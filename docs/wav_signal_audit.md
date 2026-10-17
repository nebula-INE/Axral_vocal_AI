# WAV signal audit

The signal audit is intentionally separate from the RIFF metadata parser. It reads PCM WAV samples locally in bounded chunks and reports peak/RMS amplitude, digital silence, near-silence (default RMS below 0.001 normalized amplitude, approximately -60 dBFS), and suspected clipping. The threshold is a heuristic and may flag intentionally quiet or silent samples. The voicebank report summary also counts unique WAV files with signal findings, digital silence, near-silence, and suspected clipping; these counts are file-level indicators, not a score of voicebank quality.

Non-PCM or unsupported formats are marked unsupported rather than decoded incorrectly. This is not phoneme recognition, speech-quality scoring, or a guarantee that an alias contains the intended pronunciation. No audio is uploaded or modified.
