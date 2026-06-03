# app/utils/shortcode.py

import secrets
import string

# Base62 alphabet — URL-safe, visually unambiguous
# We use the full set here; production systems sometimes remove
# visually similar chars (0/O, 1/l/I) for human-readable codes
ALPHABET = string.ascii_letters + string.digits  # a-z A-Z 0-9 = 62 chars


def generate_short_code(length: int = 7) -> str:
    """
    Generate a cryptographically random base62 short code.
    
    Why secrets.choice instead of random.choice?
    - secrets module uses the OS's CSPRNG (cryptographically secure
      pseudorandom number generator)
    - random module is NOT cryptographically secure — it's seedable
      and predictable if the seed is known
    - For URL shorteners, predictable codes are a security issue:
      an attacker could enumerate or predict upcoming codes
    
    Why length=7?
    - 62^7 = 3,521,614,606,208 possible codes
    - At 1 million new URLs/day, collision probability stays below
      0.1% for ~3.5 billion URLs — far beyond what we'll ever hit
    
    Args:
        length: Number of characters in the short code
        
    Returns:
        A random base62 string of the given length
    """
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def is_valid_short_code(code: str) -> bool:
    """
    Validate that a short code contains only safe URL characters.
    Used to validate custom codes from user input before DB insertion.
    """
    if not code or not isinstance(code, str):
        return False
    allowed = set(ALPHABET + "-_")  # Allow hyphens and underscores for custom codes
    return all(c in allowed for c in code)