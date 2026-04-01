# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *

import json
import typing


class EngageChain(gl.Contract):
    submissions:  TreeMap[str, str]
    ai_responses: TreeMap[str, str]
    verdicts:     TreeMap[str, str]
    authors:      TreeMap[str, str]
    statuses:     TreeMap[str, str]
    next_id:      str

    def __init__(self):
        self.next_id = "0"

    # ── Write: submit opinion ──────────────────────────────────────────────
    @gl.public.write
    def submit_opinion(self, text: str) -> typing.Any:
        assert len(text) > 0, "Text cannot be empty"
        assert len(text) <= 2000, "Text cannot exceed 2000 characters"

        opinion_id                    = self.next_id
        self.submissions[opinion_id]  = text
        self.ai_responses[opinion_id] = ""
        self.verdicts[opinion_id]     = ""
        self.authors[opinion_id]      = gl.message.sender_address.as_hex
        self.statuses[opinion_id]     = "pending"
        self.next_id                  = str(int(self.next_id) + 1)

        return opinion_id

    # ── Write: evaluate with AI ────────────────────────────────────────────
    @gl.public.write
    def evaluate_opinion(self, opinion_id: str) -> typing.Any:
        assert opinion_id in self.submissions, "Invalid ID"
        assert self.statuses[opinion_id] == "pending", "Opinion already evaluated"

        # Read storage BEFORE the nondet block (official pattern)
        original_text = self.submissions[opinion_id]

        def get_analysis() -> typing.Any:
            task = f"""You are an expert analyst of ideas, proposals, and opinions.
Analyze this text: "{original_text}"

Respond with the following JSON format:
{{
    "summary": "brief summary in 1-2 sentences",
    "sentiment": "positive or negative or neutral or mixed",
    "category": "proposal or opinion or dispute or question or other",
    "key_points": ["point 1", "point 2", "point 3"],
    "ai_recommendation": "concrete recommendation or verdict",
    "confidence_score": "0.85"
}}
IMPORTANT RULES:
- confidence_score MUST be a string like "0.85", NOT a number.
- All values must be strings or lists of strings.
- It is mandatory that you respond only using the JSON format above,
  nothing else. Don't include any other words or characters.
- Your output must be only JSON without any formatting prefix or suffix.
- This result should be perfectly parsable by a JSON parser without errors."""

            result = (
                gl.nondet.exec_prompt(task)
                .replace("```json", "")
                .replace("```", "")
                .strip()
            )
            print(result)
            parsed = json.loads(result)

            # FIX ERROR 2: GenLayer calldata cannot encode Python float.
            # Convert confidence_score to str regardless of what the LLM returned.
            # This is the root cause that cascades into Error 1 and Error 3.
            raw_score = parsed.get("confidence_score", "0")
            parsed["confidence_score"] = str(raw_score)

            # Defensive: ensure all values are calldata-safe types (str, list, dict)
            for key in ["summary", "sentiment", "category", "ai_recommendation"]:
                if key in parsed and not isinstance(parsed[key], str):
                    parsed[key] = str(parsed[key])

            if "key_points" in parsed:
                if not isinstance(parsed["key_points"], list):
                    parsed["key_points"] = [str(parsed["key_points"])]
                else:
                    parsed["key_points"] = [str(p) for p in parsed["key_points"]]

            return parsed

        result_json = gl.eq_principle.strict_eq(get_analysis)

        # Store the full result as JSON string in storage
        self.ai_responses[opinion_id] = json.dumps(result_json)
        self.statuses[opinion_id]     = "evaluated"

        return result_json

    # ── Write: finalize opinion ────────────────────────────────────────────
    @gl.public.write
    def finalize_opinion(self, opinion_id: str, verdict: str) -> typing.Any:
        assert opinion_id in self.submissions, "Invalid ID"
        assert self.statuses[opinion_id] == "evaluated", "Must be evaluated first"
        assert len(verdict) > 0, "Verdict cannot be empty"

        self.verdicts[opinion_id] = verdict
        self.statuses[opinion_id] = "finalized"

        return {"id": opinion_id, "status": "finalized"}

    # ── View: all opinions ────────────────────────────────────────────────
    @gl.public.view
    def get_all_opinions(self) -> dict[str, typing.Any]:
        return {k: v for k, v in self.submissions.items()}

    # ── View: full data for one entry ─────────────────────────────────────
    @gl.public.view
    def get_resolution_data(self, opinion_id: str) -> dict[str, typing.Any]:
        assert opinion_id in self.submissions, "Invalid ID"
        return {
            "id":          opinion_id,
            "text":        self.submissions[opinion_id],
            "ai_response": self.ai_responses[opinion_id],
            "verdict":     self.verdicts[opinion_id],
            "status":      self.statuses[opinion_id],
            "author":      self.authors[opinion_id],
        }

    # ── View: total submissions ───────────────────────────────────────────
    @gl.public.view
    def get_total_submissions(self) -> str:
        return self.next_id

    # ── View: status ──────────────────────────────────────────────────────
    @gl.public.view
    def get_status(self, opinion_id: str) -> str:
        assert opinion_id in self.submissions, "Invalid ID"
        return self.statuses[opinion_id]
