"""
AI Engine - Powered by Groq API (Llama 3.3 70B)
Content moderation, Q&A, spam detection
"""

import httpx, json, logging, re
logger = logging.getLogger(__name__)

# ── Fast pattern filter (before API call) ────────────────────────
_BAD = [
    # Hindi/Hinglish
    "madarchod","bhenchod","chutiya","randi","harami","gaandu","bhosdike",
    "lodu","lauda","lund","chut","bkl","bc","mc","mf","bsdk","bhosdi",
    "gandu","chodu","saala","kamina","kutti","haramzada","bakrichod",
    # English
    "fuck","shit","bitch","asshole","bastard","cunt","whore","nigger",
    "faggot","motherfucker","dickhead","pussy","cock","penis","vagina",
    # Adult
    "porn","xxx","nude","naked","sex video","nudes","onlyfans",
    "escort","prostitute","sexy photo","adult content",
]
_PAT = re.compile(
    r'\b(' + '|'.join(re.escape(w) for w in _BAD) + r')\b',
    re.IGNORECASE
)

class AIEngine:
    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        self.api_key = api_key
        self.model   = model
        self.url     = "https://api.groq.com/openai/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json"
        }

    async def _call(self, messages: list, max_tokens=600, temperature=0.4) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False
        }
        async with httpx.AsyncClient(timeout=25.0) as c:
            r = await c.post(self.url, headers=self.headers, json=payload)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()

    # ── Content Moderation ────────────────────────────────────────
    async def check_content_violation(self, text: str) -> dict:
        # Fast local check first
        m = _PAT.search(text)
        if m:
            word = m.group()
            vtype = "Adult Content" if any(
                w in word.lower() for w in ["porn","xxx","nude","sex","escort","onlyfans"]
            ) else "Abusive Language"
            return {
                "is_violation": True,
                "type": vtype,
                "reason": f"Prohibited word detected: '{word}'",
                "severity": "high",
                "method": "pattern"
            }

        if len(text) < 4 or text.startswith("/"):
            return {"is_violation": False}

        # AI deep check
        try:
            msgs = [
                {
                    "role": "system",
                    "content": (
                        "You are a strict Telegram group content moderator. "
                        "Check messages for: abusive language (any language), adult/sexual content, "
                        "hate speech, threats, or scam links. "
                        "Respond ONLY with valid JSON, no extra text:\n"
                        '{"is_violation": true/false, "type": "category or null", '
                        '"reason": "brief reason or null", "severity": "low/medium/high or null"}'
                    )
                },
                {"role": "user", "content": f"Check: {text[:400]}"}
            ]
            raw = await self._call(msgs, max_tokens=120, temperature=0.1)
            raw = raw.strip().strip("```json").strip("```").strip()
            result = json.loads(raw)
            result["method"] = "ai"
            return result
        except Exception as e:
            logger.error(f"Moderation check error: {e}")
            return {"is_violation": False}

    # ── Q&A ───────────────────────────────────────────────────────
    async def answer_question(self, question: str, user_name="", chat_title="") -> str:
        ctx = f"Group: {chat_title}. " if chat_title else ""
        msgs = [
            {
                "role": "system",
                "content": (
                    f"You are a helpful AI assistant in a Telegram group. {ctx}"
                    f"User's name: {user_name or 'User'}. "
                    "Reply in the same language as the question (Hindi/Hinglish/English). "
                    "Be concise (3-5 sentences), accurate, and friendly. "
                    "No emojis. Professional tone. "
                    "For code questions, provide clean code examples."
                )
            },
            {"role": "user", "content": question}
        ]
        return await self._call(msgs, max_tokens=700, temperature=0.6)

    # ── General Generation ────────────────────────────────────────
    async def generate_response(self, prompt: str) -> str:
        msgs = [{"role": "user", "content": prompt}]
        return await self._call(msgs, max_tokens=300, temperature=0.7)

    # ── Question Detection ────────────────────────────────────────
    async def is_question_needing_answer(self, text: str) -> bool:
        if len(text) < 8:
            return False
        indicators = [
            "?","kya","kaise","kyun","kab","kaun","kahan","batao","bata",
            "what","how","why","when","where","who","which","help","explain",
            "difference","matlab","meaning","samjhao","suggest","recommend",
            "kya hai","kya hota","tell me","can you","could you"
        ]
        tl = text.lower()
        return any(w in tl for w in indicators)

    # ── Spam Detection ────────────────────────────────────────────
    async def analyze_spam(self, text: str, count: int) -> dict:
        spam_words = [
            "join karo","click here","free money","earn daily",
            "t.me/+","bit.ly","tinyurl","whatsapp group",
            "subscribe karo","follow karo","like share",
            "refer karo","referral link","paisa kamao",
        ]
        tl = text.lower()
        score = sum(1 for w in spam_words if w in tl)

        # Excessive caps
        if len(text) > 15 and sum(1 for c in text if c.isupper()) / len(text) > 0.65:
            score += 1

        # Repeated chars
        if re.search(r'(.)\1{5,}', text):
            score += 1

        # Too many links
        if len(re.findall(r'https?://', text)) > 2:
            score += 2

        return {
            "is_spam": score >= 2,
            "spam_score": score,
            "reason": "Spam or promotional content detected" if score >= 2 else None
        }
