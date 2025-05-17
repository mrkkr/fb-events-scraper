import logging
import json
import aiohttp

class LLMEventParser:
    """
    LLM-based event parser using Ollama's local API
    """
    def __init__(self):
        self.llm_url = "http://localhost:11434/api/generate"
        self.headers = {"Content-Type": "application/json"}
        self.prompt_template = """Extract these fields from HTML as JSON:
{{
  "date_time": "extracted date/time",
  "title": "event title",
  "place": "event location",
  "url": "event URL"
}}

HTML content: {html_content}

Return ONLY valid JSON without any formatting or comments:"""

    async def parse_with_llm(self, html_content: str) -> dict:
        """Parse HTML content using local LLM"""
        try:
            prompt = self.prompt_template.format(html_content=html_content[:1500])  # Truncate for Pi's memory
            
            data = {
                "model": "tinydolphin",
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.1}
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(self.llm_url, json=data, headers=self.headers) as response:
                    result = await response.json()
                    return json.loads(result["response"].strip())

        except Exception as e:
            logging.error(f"LLM parsing failed: {str(e)}")
            return {}
