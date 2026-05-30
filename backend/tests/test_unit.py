import unittest
from fastapi.testclient import TestClient

from main import app
from app.config import settings
from app.models.channel import ChannelModel
from app.database import mongo_client
from app.cache import redis_client

class TestHydraStreamUnit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create TestClient and enter context to trigger FastAPI startup events (db/cache init) in the correct event loop
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        # Exit context to trigger FastAPI shutdown events
        cls.client.__exit__(None, None, None)

    def test_config_loading(self):
        """Verify that configuration settings load successfully with appropriate defaults."""
        self.assertEqual(settings.APP_NAME, "HydraStream Backend")
        self.assertIn("hydra_stream", settings.MONGO_DB)
        self.assertGreater(settings.MAX_CONCURRENT_VALIDATORS, 0)
        self.assertGreater(settings.MAX_CONCURRENT_FFPROBE, 0)

    def test_channel_model_generation(self):
        """Verify that ChannelModel.to_db compiles correct schema properties."""
        channel_data = ChannelModel.to_db(
            name="Test TV",
            stream_url="https://example.com/test.m3u8",
            logo="https://example.com/logo.png",
            country="IN",
            language="Hindi",
            category="News",
            status="working",
            latency=150.5,
            resolution="1080p",
            tvg_id="test_tv_in",
            group_title="News",
            stream_format="hls"
        )
        
        self.assertEqual(channel_data["_id"], "test_tv_in")
        self.assertEqual(channel_data["name"], "Test TV")
        self.assertEqual(channel_data["country"], "IN")
        self.assertEqual(channel_data["language"], "Hindi")
        self.assertEqual(channel_data["category"], "News")
        self.assertEqual(channel_data["status"], "working")
        self.assertEqual(channel_data["latency"], 150.5)
        self.assertEqual(channel_data["resolution"], "1080p")
        self.assertTrue(channel_data["active"])

    def test_health_endpoint(self):
        """Verify that root health endpoint returns online status and endpoint list."""
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "online")
        self.assertEqual(data["app"], "HydraStream Backend")
        self.assertIn("api_v1_channels", data["endpoints"])

    def test_categories_endpoint(self):
        """Verify categories API responds with valid array."""
        resp = self.client.get("/api/v1/categories")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)

    def test_countries_endpoint(self):
        """Verify countries API responds with valid array."""
        resp = self.client.get("/api/v1/countries")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)

    def test_languages_endpoint(self):
        """Verify languages API responds with valid array."""
        resp = self.client.get("/api/v1/languages")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)

    def test_channels_paginated_endpoint(self):
        """Verify that /channels responds with correct pagination schemas."""
        resp = self.client.get("/api/v1/channels?page=1&limit=5")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("total", data)
        self.assertIn("channels", data)
        self.assertIn("page", data)
        self.assertIn("limit", data)
        self.assertIsInstance(data["channels"], list)

    def test_channels_non_paginated_endpoint(self):
        """Verify that calling /channels without limit query parameter returns all channels from db."""
        resp = self.client.get("/api/v1/channels")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("total", data)
        self.assertIn("channels", data)
        self.assertIn("page", data)
        self.assertIn("limit", data)
        self.assertEqual(data["limit"], data["total"])
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["pages"], 1)
        self.assertIsInstance(data["channels"], list)

    def test_channels_search_endpoint(self):
        """Verify search matches format constraints."""
        resp = self.client.get("/api/v1/search?q=test&limit=2")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("channels", data)

    def test_fastest_channels_endpoint(self):
        """Verify fastest channels list responds with an array."""
        resp = self.client.get("/api/v1/channels/fastest?limit=3")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)

    def test_trending_channels_endpoint(self):
        """Verify trending channels responds with valid array list."""
        resp = self.client.get("/api/v1/trending?limit=3")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)

if __name__ == "__main__":
    unittest.main()
