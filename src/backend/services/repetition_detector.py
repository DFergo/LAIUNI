"""Model repetition loop detector for streaming output.

Analyzes accumulated LLM output during streaming to detect generation
loops where the model repeats the same phrase or paragraph.

DESIGN PRINCIPLE: Conservative. False positives (cutting legitimate
responses) are MUCH worse than false negatives (letting some repetition
through). Better to miss a loop than to cut a valid response.

Thresholds are set high intentionally:
- MIN_PHRASE_LENGTH = 40 chars — ignores short repeated phrases that
  could be legitimate (list items, similar framework descriptions)
- MIN_REPETITIONS = 3 — requires the phrase to appear 3+ times before
  triggering, ruling out natural echo (e.g., "ILO Convention X... ILO Convention Y")
- Only checks after 200+ chars accumulated — don't analyze short responses

If this detector triggers incorrectly on legitimate content, RAISE the
thresholds rather than disabling it. Document the case in lessons-learned.md.
"""

import logging

logger = logging.getLogger("backend.repetition")

# Minimum length of a repeated phrase to count as a loop (chars).
# Short repeated strings are common in legitimate output (bullet points,
# framework names, numbered lists). Only flag substantial repetitions.
MIN_PHRASE_LENGTH = 40

# How many times a phrase must repeat to trigger detection.
# 3 means the SAME substantial phrase appears 3+ times — this is very
# unlikely in legitimate content.
MIN_REPETITIONS = 3

# Minimum accumulated output before we start checking (chars).
# Short responses can't have meaningful repetition loops.
MIN_OUTPUT_LENGTH = 200


class RepetitionDetector:
    """Stateful detector for a single streaming response.

    Create one per LLM call. Feed chunks via `check()`. When a loop is
    detected, `check()` returns True.
    """

    def __init__(self):
        self._buffer: str = ""
        self._triggered: bool = False

    @property
    def triggered(self) -> bool:
        return self._triggered

    @property
    def buffer(self) -> str:
        return self._buffer

    def check(self, new_chunk: str) -> bool:
        """Add a chunk and check for repetition loops.

        Returns True if a loop is detected. Once triggered, always
        returns True (no recovery within a single response).
        """
        if self._triggered:
            return True

        self._buffer += new_chunk

        # Don't check short outputs
        if len(self._buffer) < MIN_OUTPUT_LENGTH:
            return False

        # Check for repeated substrings using a sliding window approach.
        # We look for any substring of MIN_PHRASE_LENGTH that appears
        # MIN_REPETITIONS or more times in the accumulated output.
        #
        # Performance note: this runs on every chunk, but the buffer is
        # bounded by LLM max_tokens (typically 2-4k tokens ≈ 8-16k chars).
        # The sliding window is O(n) where n = buffer length. At 16k chars
        # with step=20, that's ~800 iterations per check — negligible
        # compared to LLM inference latency.

        text = self._buffer
        text_len = len(text)

        # Step through the text looking for repeated phrases
        # Use a step > 1 to reduce iterations (we don't need char-by-char)
        step = 20
        for i in range(0, text_len - MIN_PHRASE_LENGTH, step):
            phrase = text[i:i + MIN_PHRASE_LENGTH]

            # Count occurrences of this phrase in the full text
            count = 0
            search_start = 0
            while True:
                pos = text.find(phrase, search_start)
                if pos == -1:
                    break
                count += 1
                if count >= MIN_REPETITIONS:
                    # Loop detected
                    self._triggered = True
                    logger.warning(
                        f"Repetition loop detected: phrase '{phrase[:50]}...' "
                        f"repeated {count}+ times in {text_len} chars"
                    )
                    return True
                search_start = pos + 1

        return False

    def get_clean_output(self) -> str:
        """Get the output up to the point where repetition started.

        Returns the buffer content up to the second occurrence of the
        repeated phrase (keeping the first two as they might be
        legitimate), or the full buffer if not triggered.
        """
        if not self._triggered:
            return self._buffer

        # Find the repeated phrase and cut before the 3rd occurrence
        text = self._buffer
        text_len = len(text)
        step = 20

        for i in range(0, text_len - MIN_PHRASE_LENGTH, step):
            phrase = text[i:i + MIN_PHRASE_LENGTH]
            count = 0
            positions = []
            search_start = 0
            while True:
                pos = text.find(phrase, search_start)
                if pos == -1:
                    break
                count += 1
                positions.append(pos)
                if count >= MIN_REPETITIONS:
                    # Cut before the 3rd occurrence
                    cut_point = positions[2]
                    clean = text[:cut_point].rstrip()
                    logger.info(f"Trimmed output at position {cut_point}/{text_len}")
                    return clean
                search_start = pos + 1

        # Fallback: return full buffer
        return self._buffer
