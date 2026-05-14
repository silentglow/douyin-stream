"""敏感数据加密存储工具

使用 Fernet 对称加密算法对敏感数据进行加密存储，
确保 cookie、认证凭证等敏感信息不会以明文形式存储在数据库中。
"""
from cryptography.fernet import Fernet, InvalidToken
from media_tools.core.config import SystemSettings
from media_tools.logger import get_logger

logger = get_logger(__name__)

_ENCRYPTION_KEY_CONFIG_KEY = "encryption_key"


class SecureStorage:
    """敏感数据加密存储工具"""

    @staticmethod
    def _get_or_create_key() -> bytes:
        """获取或创建加密密钥
        
        优先从配置中读取密钥，如果不存在则生成新密钥并保存。
        
        Returns:
            加密密钥（bytes）
        """
        key = SystemSettings.get(_ENCRYPTION_KEY_CONFIG_KEY)
        if key:
            return key.encode()
        
        logger.info("首次使用加密功能，生成新的加密密钥...")
        key = Fernet.generate_key()
        SystemSettings.set(_ENCRYPTION_KEY_CONFIG_KEY, key.decode())
        return key

    @staticmethod
    def encrypt(data: str) -> str:
        """加密字符串
        
        Args:
            data: 要加密的明文数据
            
        Returns:
            加密后的字符串
            
        Raises:
            ValueError: 如果数据为空
        """
        if not data:
            return ""
            
        try:
            f = Fernet(SecureStorage._get_or_create_key())
            return f.encrypt(data.encode()).decode()
        except Exception as e:
            logger.error(f"加密失败: {e}")
            raise

    @staticmethod
    def decrypt(data: str) -> str:
        """解密字符串
        
        Args:
            data: 要解密的密文数据
            
        Returns:
            解密后的明文字符串
            
        Raises:
            ValueError: 如果解密失败
        """
        if not data:
            return ""
            
        try:
            f = Fernet(SecureStorage._get_or_create_key())
            return f.decrypt(data.encode()).decode()
        except InvalidToken:
            logger.error("解密失败：无效的令牌或密钥不匹配")
            raise ValueError("解密失败：无效的令牌或密钥不匹配")
        except Exception as e:
            logger.error(f"解密失败: {e}")
            raise

    @staticmethod
    def is_encrypted(data: str) -> bool:
        """判断数据是否已加密
        
        通过检查数据格式是否符合 Fernet 加密格式来判断。
        
        Args:
            data: 待检查的数据
            
        Returns:
            True 如果数据看起来已加密，False 否则
        """
        if not data:
            return False
            
        try:
            parts = data.split('.')
            # Fernet 格式：base64url(version) + "." + base64url(timestamp) + "." + base64url(ciphertext) + "." + base64url(mac)
            return len(parts) == 4 and len(data) > 40
        except Exception:  # noqa: defensive – 格式校验失败即视为无效
            return False