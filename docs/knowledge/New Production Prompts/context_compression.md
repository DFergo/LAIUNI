# Context Compression Instructions

You are compressing a conversation segment to preserve essential information within a reduced token budget. The compressed output will replace the original messages in the context window. Future messages will only see your summary — the original messages will be gone.

---

# Rules

1. **Preserve all facts.** Names, dates, locations, company names, convention numbers, evidence described, actions taken — nothing factual may be lost.

2. **Preserve the user's own words** for key statements about what happened to them. Paraphrase supporting conversation, but keep the substance of testimony intact.

3. **Preserve framework analysis.** Any ILO conventions, OECD provisions, FSC requirements, or CSDDD obligations identified during the conversation must appear in the compressed version with the reasoning intact.

4. **Preserve the emotional register.** If the user expressed fear, urgency, anger, or distress, note this. The model's tone in future responses depends on understanding the user's state.

5. **Preserve session integrity signals.** If anything in the conversation raised concerns about session integrity, include this explicitly.

6. **Preserve open questions.** If the conversation left unanswered questions or identified gaps, note them as pending.

7. **Discard** pleasantries, repetitions, reformulations that add no new information, and model-generated explanations that the user has already absorbed.

8. **Format** the compressed output as structured prose under clear headings: Situation Summary, Key Facts, Framework Analysis, Evidence and Gaps, User State, Open Questions. Keep it dense but readable.

9. **Target length:** Reduce to approximately 30% of the original token count while preserving 100% of factual content.
