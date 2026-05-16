from app.models import YoutubeDownload
from app.repositories.base import TenantScopedRepository


class YoutubeDownloadRepository(TenantScopedRepository[YoutubeDownload]):
    """YouTube 下載記錄的租戶隔離存取層。"""

    model = YoutubeDownload
