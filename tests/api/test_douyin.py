from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from media_tools.api.app import app

client = TestClient(app)


@patch("media_tools.api.routers.douyin.SecUserIdFetcher.get_sec_user_id", new_callable=AsyncMock)
@patch("media_tools.api.routers.douyin.DouyinHandler.fetch_user_profile", new_callable=AsyncMock)
@patch("media_tools.api.routers.douyin.DouyinHandler.fetch_user_post_videos")
def test_get_metadata(mock_fetch_user_post_videos, mock_fetch_user_profile, mock_get_sec_user_id):
    # Mock sec_user_id
    mock_get_sec_user_id.return_value = "MS4wLjABAAAAQ09FeL2ALZletbVLqDXBPDKuu76XXy6xvdkszy2PLiZR-SI5-VO3TEQSkzB92aKb"

    # Mock user_profile
    class MockProfile:
        nickname = "Test User"
        avatar_larger = "https://example.com/avatar.jpg"

    mock_fetch_user_profile.return_value = MockProfile()

    # Mock user_post async generator
    async def mock_generator(*args, **kwargs):
        class MockAweme:
            aweme_id = "1234567890"
            desc = "Test Video"
            create_time = 1620000000
            video_play_addr = {"cover": "https://example.com/cover.jpg"}

        yield MockAweme()

    mock_fetch_user_post_videos.side_effect = mock_generator

    url = "https://douyin.com/user/MS4wLjABAAAAQ09FeL2ALZletbVLqDXBPDKuu76XXy6xvdkszy2PLiZR-SI5-VO3TEQSkzB92aKb"
    response = client.get(f"/api/v1/douyin/metadata?url={url}&max_counts=5")
    assert response.status_code == 200
    data = response.json()
    assert "creator" in data
    assert "videos" in data
    assert isinstance(data["videos"], list)
