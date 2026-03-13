"""
Platform detection utilities for SteamKM2
Auto-detects platform type from game keys
"""

import re
from typing import Optional

class PlatformDetector:
    """Detects platform type from game keys"""
    
    # Platform patterns - order matters for specificity
    PLATFORM_PATTERNS = [
        # Steam keys (actual Steam format: XXXXX-XXXXX-XXXXX, 5 chars each segment)
        (r'^[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}$', 'Steam'),
        
        # Epic Games Store (32 char hex or UUID format)
        (r'^[A-Z0-9]{32}$', 'Epic Games'),
        (r'^[A-Z0-9]{8}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{12}$', 'Epic Games'),
        
        # Origin/EA (5 segments of 4 characters each: XXXX-XXXX-XXXX-XXXX-XXXX)
        (r'^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$', 'Origin/EA'),
        (r'origin\.com', 'Origin/EA'),
        
        # Ubisoft Connect (3 segments of 4 characters: XXXX-XXXX-XXXX)
        (r'^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$', 'Ubisoft'),
        (r'ubisoft\.com', 'Ubisoft'),
        
        # GOG (8-16 character codes, no dashes)
        (r'^[A-Z0-9]{8,16}$', 'GOG'),
        (r'gog\.com', 'GOG'),
        
        # Battle.net
        (r'battle\.net', 'Battle.net'),
        (r'blizzard\.com', 'Battle.net'),
        
        # Xbox/Microsoft Store
        (r'^[A-Z0-9]{25}$', 'Xbox'),
        (r'xbox\.com', 'Xbox'),
        (r'microsoft\.com', 'Xbox'),
        
        # PlayStation
        (r'^[A-Z0-9]{12}$', 'PlayStation'),
        (r'playstation\.com', 'PlayStation'),
        (r'sony\.com', 'PlayStation'),
        
        # Nintendo
        (r'nintendo\.com', 'Nintendo'),
            
        # URLs
        (r'^https?://', 'Web Link'),
    ]
    
    @staticmethod
    def detect_platform(key: str) -> str:
        """
        Detect platform from a game key
        
        Args:
            key: The game key to analyze
            
        Returns:
            Platform name or 'Unknown' if not detected
        """
        if not key:
            return 'Unknown'
        
        # Clean the key - remove whitespace and convert to uppercase for pattern matching
        clean_key = key.strip().upper()
        original_key = key.strip()  # Keep original case for URL matching
        
        # Check each pattern
        for pattern, platform in PlatformDetector.PLATFORM_PATTERNS:
            # Use original case for URL patterns, uppercase for others
            test_key = original_key if any(url_char in pattern for url_char in ['.', 'http']) else clean_key
            
            if re.search(pattern, test_key, re.IGNORECASE):
                return platform
        
        # Special cases based on length and character patterns
        if len(clean_key) == 16 and clean_key.isalnum():
            return 'GOG'
        elif len(clean_key) == 32 and clean_key.isalnum():
            return 'Epic Games'
        elif len(clean_key) > 50:
            return 'Unknown (Long Key)'
        
        return 'Unknown'
    
    @staticmethod
    def get_all_platforms() -> list:
        """Get list of all known platforms"""
        platforms = set()
        for _, platform in PlatformDetector.PLATFORM_PATTERNS:
            platforms.add(platform)
        platforms.add('Unknown')
        return sorted(list(platforms))
    
    @staticmethod
    def validate_key_format(key: str, expected_platform: Optional[str] = None) -> bool:
        """
        Validate if a key matches expected platform format
        
        Args:
            key: The key to validate
            expected_platform: Expected platform (optional)
            
        Returns:
            True if valid format, False otherwise
        """
        if not key:
            return False
        
        detected_platform = PlatformDetector.detect_platform(key)
        
        if expected_platform:
            return detected_platform.lower() == expected_platform.lower()
        
        return detected_platform != 'Unknown'