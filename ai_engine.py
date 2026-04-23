"""
AI Engine - Powered by Grok (xAI) API
Handles content moderation, Q&A, and intelligent responses.
"""

import httpx
import json
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Adult/Bad Word Patterns (Fast Pre-check before AI) ─────────
QUICK_FILTER_WORDS = [
    # Hindi/Hinglish gali words (common variations)
    "madarchod", "bhenchod", "chutiya", "randi", "harami", "saala",
    "gaandu", "bhosdike", "lodu", "lauda", "lund", "chut", "bkl",
    "bc", "mc", "mf", "bsdk", "bhosdi", "gandu", "chodu",
    # English
    "fuck", "shit", "bitch", "asshole", "bastard", "cunt", "whore",
    "nigger", "faggot", "motherfucker", "dickhead", "pussy",
    # Adult content keywords
    "porn", "xxx", "nude", "naked", "sex video", "sexy photo",
    "nudes", "onlyfans", "escort", "prostitute",
]

COMPILED_PATTERN = re.compile(
    r'\b(' + '|'.join(re.escape(w) for w in QUICK_FILTER_WORDS) + r')\b',
    re.IGNORECASE
)


class AIEngine:
    def __init__(self, api_key: str, model: str = "grok-3-mini"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.x.ai/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    async def _call_grok(self, messages: list, max_tokens: int = 500, temperature: float = 0.3) -> str:
        """Make API call to Grok."""
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.base_url,
                headers=self.headers,
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
    
    async def check_content_violation(self, text: str) -> dict:
        """
        Check if message contains violations.
        Returns: {is_violation: bool, type: str, reason: str, severity: str}
        Uses fast pattern match first, then AI for edge cases.
        """
        # Fast pattern check first
        quick_match = COMPILED_PATTERN.search(text)
        if quick_match:
            matched_word = quick_match.group()
            # Determine type
            if any(w in matched_word.lower() for w in ["porn", "xxx", "nude", "sex", "escort", "onlyfans"]):
                vtype = "Adult Content"
            else:
                vtype = "Abusive Language / Gali"
            
            return {
                "is_violation": True,
                "type": vtype,
                "reason": f"'{matched_word}' word detected — group rules violation",
                "severity": "high",
                "method": "pattern"
            }
        
        # AI deep-check for subtle violations
        if len(text) < 5 or text.startswith('/'):
            return {"is_violation": False}
        
        try:
            messages = [
                {
                    "role": "system",
                    "content": """You are a strict content moderator for a Telegram group. 
Analyze messages for violations. Respond ONLY with valid JSON.

Check for:
1. Adult/sexual content (including coded language, hints)
2. Abusive language, gali, insults in ANY language (Hindi, Hinglish, English)
3. Hate speech, discrimination
4. Spam, scam, phishing links
5. Threats or violence

Response format (JSON only, no other text):
{"is_violation": true/false, "type": "violation category or null", "reason": "brief reason or null", "severity": "low/medium/high or null"}"""
                },
                {
                    "role": "user",
                    "content": f"Check this message: {text[:500]}"
                }
            ]
            
            result = await self._call_grok(messages, max_tokens=150, temperature=0.1)
            
            # Parse JSON response
            result = result.strip()
            if result.startswith("```"):
                result = result.split("```")[1]
                if result.startswith("json"):
                    result = result[4:]
            
            parsed = json.loads(result)
            parsed["method"] = "ai"
            return parsed
            
        except (json.JSONDecodeError, httpx.HTTPError, KeyError) as e:
            logger.error(f"Content check error: {e}")
            return {"is_violation": False}
    
    async def answer_question(self, question: str, user_name: str = "", chat_title: str = "") -> str:
        """Answer a user's question intelligently."""
        context_info = ""
        if chat_title:
            context_info = f"This question is from a Telegram group called '{chat_title}'."
        
        messages = [
            {
                "role": "system",
                "content": f"""You are a helpful, friendly AI assistant in a Telegram group.
{context_info}
User's name: {user_name or 'User'}

Guidelines:
- Answer in the same language as the question (Hindi/Hinglish/English)
- Keep responses concise but complete (3-5 sentences usually)
- Be friendly and conversational, use emojis where appropriate
- For coding questions, provide clear code examples
- For general knowledge, be accurate and educational
- Don't make up information you're not sure about
- If asked about bot features, explain the available commands"""
            },
            {
                "role": "user",
                "content": question
            }
        ]
        
        return await self._call_grok(messages, max_tokens=600, temperature=0.7)
    
    async def generate_response(self, prompt: str) -> str:
        """Generate a response for a given prompt."""
        messages = [
            {"role": "user", "content": prompt}
        ]
        return await self._call_grok(messages, max_tokens=300, temperature=0.8)
    
    async def is_question_needing_answer(self, text: str) -> bool:
        """Determine if a group message is a genuine question that needs AI answer."""
        # Simple heuristics first
        question_indicators = [
            "?", "kya", "kaise", "kyun", "kab", "kaun", "kahan",
            "what", "how", "why", "when", "where", "who", "which",
            "bata", "help", "samjhao", "explain", "difference",
            "matlab", "meaning", "kya hai", "kya hota"
        ]
        
        text_lower = text.lower()
        has_indicator = any(ind in text_lower for ind in question_indicators)
        
        return has_indicator and len(text) > 10
    
    async def analyze_spam(self, text: str, user_message_count: int) -> dict:
        """Detect spam patterns."""
        spam_indicators = [
            "join karo", "click here", "free money", "earn daily",
            "http://", "https://t.me/+", "bit.ly", "tinyurl",
            "whatsapp group", "telegram channel link", "subscribe karo",
            "follow karo", "like karo", "share karo"
        ]
        
        text_lower = text.lower()
        spam_score = sum(1 for ind in spam_indicators if ind in text_lower)
        
        # Check for excessive caps
        if len(text) > 20:
            caps_ratio = sum(1 for c in text if c.isupper()) / len(text)
            if caps_ratio > 0.7:
                spam_score += 1
        
        # Repeated characters (spammy)
        if re.search(r'(.)\1{4,}', text):
            spam_score += 1
        
        return {
            "is_spam": spam_score >= 2,
            "spam_score": spam_score,
            "reason": "Spam/promotional content detected" if spam_score >= 2 else None
        }
