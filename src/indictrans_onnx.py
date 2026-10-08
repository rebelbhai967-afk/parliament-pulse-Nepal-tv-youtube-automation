#!/usr/bin/env python3
"""Self-contained IndicTrans2 ONNX inference helper.

Uses the public MIT-licensed ONNX export of AI4Bharat IndicTrans2's
Indic-to-English model. No paid translation API or API key is required.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Union
import shutil
import tempfile
import os

import numpy as np

logger = logging.getLogger(__name__)


def _past_feed(past_outputs: list[np.ndarray], num_layers: int) -> dict[str, np.ndarray]:
    feed: dict[str, np.ndarray] = {}
    for i in range(num_layers):
        base = i * 4
        feed[f"past_key_values.{i}.decoder.key"] = past_outputs[base]
        feed[f"past_key_values.{i}.decoder.value"] = past_outputs[base + 1]
        feed[f"past_key_values.{i}.encoder.key"] = past_outputs[base + 2]
        feed[f"past_key_values.{i}.encoder.value"] = past_outputs[base + 3]
    return feed


class IndicTransONNX:
    """Load an IndicTrans2 ONNX bundle and run greedy translation."""

    def __init__(
        self,
        model_path: Union[str, Path],
        providers: list[str] | None = None,
    ) -> None:
        import onnxruntime as ort
        from tokenizers import Tokenizer
        from IndicTransToolkit import IndicProcessor

        model_path = str(model_path)
        if "/" in model_path and not Path(model_path).exists():
            from huggingface_hub import snapshot_download
            logger.info("Downloading snapshot for %s ...", model_path)
            model_path = snapshot_download(repo_id=model_path)

        snap = Path(model_path)
        # Hugging Face snapshots may use symlinks into the shared blob cache.
        # ONNX Runtime validates external-data files against the real model
        # directory and can reject those symlinked paths as escaping the model
        # directory. Materialize the snapshot into a normal local directory so
        # each .onnx file and its matching .onnx.data file live together.
        self._materialized_dir: Path | None = None
        if snap.exists() and snap.is_dir():
            materialized = Path(tempfile.mkdtemp(prefix="indictrans2-onnx-"))
            for src in snap.iterdir():
                if src.is_file():
                    shutil.copy2(src, materialized / src.name, follow_symlinks=True)
            snap = materialized
            self._materialized_dir = materialized

        self._providers = providers or ["CPUExecutionProvider"]
        self._ip = IndicProcessor(inference=True)

        self._src_tok = Tokenizer.from_file(str(snap / "tokenizer_src.json"))
        self._tgt_tok = Tokenizer.from_file(str(snap / "tokenizer_tgt.json"))
        self._meta: dict = json.loads(
            (snap / "tokenizer_meta.json").read_text(encoding="utf-8")
        )

        gen_cfg: dict = {}
        gen_path = snap / "generation_config.json"
        if gen_path.exists():
            gen_cfg = json.loads(gen_path.read_text(encoding="utf-8"))
        self._decoder_start_id = int(gen_cfg.get("decoder_start_token_id", 2))
        self._eos_id = int(gen_cfg.get("eos_token_id", 2))

        self._enc = ort.InferenceSession(
            str(snap / "encoder_model.onnx"), providers=self._providers
        )
        self._dec = ort.InferenceSession(
            str(snap / "decoder_model.onnx"), providers=self._providers
        )
        self._dec_past = ort.InferenceSession(
            str(snap / "decoder_with_past_model.onnx"), providers=self._providers
        )
        self._num_layers = (len(self._dec.get_outputs()) - 1) // 4
        self._repetition_penalty = float(os.environ.get(
            "INDICTRANS_REPETITION_PENALTY", "1.10"
        ))
        self._no_repeat_ngram = int(os.environ.get(
            "INDICTRANS_NO_REPEAT_NGRAM", "3"
        ))

    def translate(
        self,
        text: str,
        src_lang: str = "npi_Deva",
        tgt_lang: str = "eng_Latn",
        max_new_tokens: int = 128,
    ) -> str:
        if not text.strip():
            return ""

        # Use the official IndicProcessor path. IndicTrans2 uses a shared
        # Devanagari representation internally and requires preprocessing
        # before tokenization and postprocessing after decoding.
        if hasattr(self._ip, "_placeholder_entity_maps"):
            self._ip._placeholder_entity_maps.queue.clear()
        prefixed = self._ip.preprocess_batch(
            [text], src_lang=src_lang, tgt_lang=tgt_lang
        )[0]
        encoded = self._src_tok.encode(prefixed)

        input_ids = np.array(
            [[
                i if i < self._meta["src_dict_size"] else self._meta["unk_id"]
                for i in encoded.ids
            ]],
            dtype=np.int64,
        )
        attn_mask = np.array([encoded.attention_mask], dtype=np.int64)

        enc_out = self._enc.run(
            ["last_hidden_state"],
            {"input_ids": input_ids, "attention_mask": attn_mask},
        )[0]

        decoder_input_ids = np.array([[self._decoder_start_id]], dtype=np.int64)
        output_ids = [self._decoder_start_id]
        past_outputs: list[np.ndarray] | None = None

        for step in range(max_new_tokens):
            if step == 0:
                dec_out = self._dec.run(
                    None,
                    {
                        "input_ids": decoder_input_ids,
                        "encoder_hidden_states": enc_out,
                        "encoder_attention_mask": attn_mask,
                    },
                )
            else:
                assert past_outputs is not None
                dec_out = self._dec_past.run(
                    None,
                    {
                        "input_ids": decoder_input_ids,
                        "encoder_attention_mask": attn_mask,
                        **_past_feed(past_outputs, self._num_layers),
                    },
                )

            logits = np.array(dec_out[0][0, -1, :], dtype=np.float32, copy=True)
            past_outputs = list(dec_out[1:])

            # Penalize tokens already generated so noisy fragments do not fall
            # into deterministic repetition loops.
            penalty = self._repetition_penalty
            if penalty > 1.0:
                for token_id in set(output_ids):
                    if 0 <= token_id < logits.shape[0]:
                        if logits[token_id] < 0:
                            logits[token_id] *= penalty
                        else:
                            logits[token_id] /= penalty

            # Block an exact repeated n-gram before greedy selection.
            n = self._no_repeat_ngram
            if n >= 2 and len(output_ids) >= n - 1:
                prefix = output_ids[-(n - 1):]
                for i in range(len(output_ids) - n + 1):
                    if output_ids[i:i + n - 1] == prefix:
                        blocked = output_ids[i + n - 1]
                        if 0 <= blocked < logits.shape[0]:
                            logits[blocked] = -np.inf

            next_id = int(np.argmax(logits))
            output_ids.append(next_id)
            if next_id == self._eos_id:
                break
            decoder_input_ids = np.array([[next_id]], dtype=np.int64)

        safe_ids = [
            i if i < self._meta["tgt_dict_size"] else self._meta["unk_id"]
            for i in output_ids
        ]
        raw_decoded = self._tgt_tok.decode(safe_ids, skip_special_tokens=True)
        return self._ip.postprocess_batch([raw_decoded], lang=tgt_lang)[0]
