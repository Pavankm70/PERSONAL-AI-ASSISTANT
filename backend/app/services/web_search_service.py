import httpx
from typing import Dict, Any, List
from app.core.config import settings

class WebSearchService:
    """
    Live web search intelligence service using Tavily API.
    Does not fabricate or return static mocked results if unconfigured.
    """
    async def search(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        api_key = settings.WEB_SEARCH_API_KEY
        if not api_key:
            return {
                "status": "unconfigured",
                "query": query,
                "message": "Live web search is unconfigured. To enable real internet search, add WEB_SEARCH_API_KEY in backend/.env.",
                "results": []
            }

        url = "https://api.tavily.com/search"
        payload = {
            "api_key": api_key,
            "query": query,
            "search_depth": "basic",
            "include_answer": True,
            "max_results": min(max_results, 8)
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 401:
                    return {
                        "status": "error",
                        "query": query,
                        "message": "Invalid WEB_SEARCH_API_KEY provided for Tavily Search.",
                        "results": []
                    }
                if res.status_code != 200:
                    return {
                        "status": "error",
                        "query": query,
                        "message": f"Web search service returned status {res.status_code}.",
                        "results": []
                    }

                data = res.json()
                raw_results = data.get("results", [])
                formatted_results = []
                for r in raw_results:
                    formatted_results.append({
                        "title": r.get("title", "Untitled Source"),
                        "url": r.get("url", ""),
                        "snippet": r.get("content", "")[:300],
                        "score": r.get("score", 1.0)
                    })

                return {
                    "status": "success",
                    "query": query,
                    "answer": data.get("answer"),
                    "count": len(formatted_results),
                    "results": formatted_results
                }
        except Exception as e:
            return {
                "status": "error",
                "query": query,
                "message": f"Web search request failed: {str(e)}",
                "results": []
            }

web_search_service = WebSearchService()
