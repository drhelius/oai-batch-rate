import time
import threading
from abc import ABC, abstractmethod
from collections import deque


class RateLimiter(ABC):
    """Abstract base class for rate limiters."""
    
    @abstractmethod
    def should_limit(self, tokens=None):
        """
        Determine if a request should be limited based on current rates.
        
        Args:
            tokens: Optional number of tokens the request will consume
            
        Returns:
            boolean: True if the request should be limited, False otherwise
        """
        pass
    
    @abstractmethod
    def record_request(self, tokens=None):
        """
        Record a successful request for rate tracking.
        
        Args:
            tokens: Optional number of tokens consumed by the request
        """
        pass
    
    @abstractmethod
    def reset(self):
        """Reset the internal state of the rate limiter."""
        pass


class FixedWindowRateLimiter(RateLimiter):
    """
    Fixed window rate limiter that tracks both requests and tokens.
    
    This implementation uses separate fixed time windows to track requests and tokens.
    It can limit based on both RPM (requests per minute) and TPM (tokens per minute).
    """
    
    def __init__(self, max_rpm=0, max_tpm=0, rpm_window_size=10, tpm_window_size=60):
        """
        Initialize the rate limiter.
        
        Args:
            max_rpm: Maximum requests per minute (0 for unlimited)
            max_tpm: Maximum tokens per minute (0 for unlimited)
            rpm_window_size: Size of the RPM window in seconds (default 10s)
            tpm_window_size: Size of the TPM window in seconds (default 60s)
        """
        self.max_rpm = max_rpm  # Maximum requests per minute
        self.max_tpm = max_tpm  # Maximum tokens per minute
        self.rpm_window_size = rpm_window_size  # Window size for RPM in seconds
        self.tpm_window_size = tpm_window_size  # Window size for TPM in seconds
        
        # Request tracking
        self.request_timestamps = deque()
        self.token_usage = deque()  # Store (timestamp, tokens) pairs
        
        # RPM window counters
        self.rpm_window_start_time = time.time()
        self.rpm_window_requests = 0
        
        # TPM window counters
        self.tpm_window_start_time = time.time()
        self.tpm_window_tokens = 0
        
        # For calculating rates
        self.current_rpm = 0
        self.current_tpm = 0
    
    def _refresh_windows(self):
        """Check if we need to start new windows and reset if needed."""
        current_time = time.time()
        
        # Refresh RPM window if needed
        if current_time - self.rpm_window_start_time >= self.rpm_window_size:
            self.rpm_window_start_time = current_time
            self.rpm_window_requests = 0
        
        # Refresh TPM window if needed
        if current_time - self.tpm_window_start_time >= self.tpm_window_size:
            self.tpm_window_start_time = current_time
            self.tpm_window_tokens = 0
            
        # Clean up old timestamps (optional, for memory efficiency)
        cutoff_time = current_time - 60  # Keep last minute of data for rate calculations
        while self.request_timestamps and self.request_timestamps[0] < cutoff_time:
            self.request_timestamps.popleft()
        
        while self.token_usage and self.token_usage[0][0] < cutoff_time:
            self.token_usage.popleft()
    
    def _calculate_rates(self):
        """Calculate current RPM and TPM based on recent history."""
        current_time = time.time()
        cutoff_time = current_time - 60  # Last minute
        
        # Count requests in the last minute
        request_count = sum(1 for ts in self.request_timestamps if ts >= cutoff_time)
        self.current_rpm = request_count
        
        # Sum tokens used in the last minute
        token_count = sum(tokens for ts, tokens in self.token_usage if ts >= cutoff_time)
        self.current_tpm = token_count
    
    def _calculate_window_limits(self):
        """Calculate the maximum allowed requests and tokens for the current windows."""
        # Calculate max requests for RPM window
        # If max_rpm is 60 and window is 10s, we allow 10 requests per window
        rpm_window_max_requests = (self.max_rpm * self.rpm_window_size) / 60 if self.max_rpm > 0 else 0
        
        # Calculate max tokens for TPM window
        # If max_tpm is 6000 and window is 60s, we allow 6000 tokens per window
        tpm_window_max_tokens = (self.max_tpm * self.tpm_window_size) / 60 if self.max_tpm > 0 else 0
        
        return rpm_window_max_requests, tpm_window_max_tokens
    
    def _calculate_window_rates(self):
        """Calculate the current rates within each window timeframe and scale to minute."""
        current_time = time.time()
        
        # Calculate RPM window rate
        rpm_window_cutoff = current_time - self.rpm_window_size
        rpm_window_request_count = sum(1 for ts in self.request_timestamps if ts >= rpm_window_cutoff)
        scaled_rpm = rpm_window_request_count * (60 / self.rpm_window_size)
        
        # Calculate TPM window rate
        tpm_window_cutoff = current_time - self.tpm_window_size
        tpm_window_token_count = sum(tokens for ts, tokens in self.token_usage if ts >= tpm_window_cutoff)
        scaled_tpm = tpm_window_token_count * (60 / self.tpm_window_size)
        
        return scaled_rpm, scaled_tpm
    
    def should_limit(self, tokens=None):
        """
        Determine if a request should be limited based on current rates.
        
        Args:
            tokens: Estimated tokens this request will use (optional)
        
        Returns:
            boolean: True if the request should be rate limited, False otherwise
        """
        self._refresh_windows()
        
        rpm_window_max_requests, tpm_window_max_tokens = self._calculate_window_limits()
        
        # Check if we've exceeded either limit
        if rpm_window_max_requests > 0 and self.rpm_window_requests >= rpm_window_max_requests:
            return True
        
        if tpm_window_max_tokens > 0 and tokens and self.tpm_window_tokens + tokens > tpm_window_max_tokens:
            return True
        
        return False
    
    def record_request(self, tokens=None):
        """
        Record a successful request with its token usage.
        
        Args:
            tokens: Number of tokens consumed by the request
        """
        current_time = time.time()
        
        # Record the request timestamp
        self.request_timestamps.append(current_time)
        
        # Record token usage if provided
        if tokens:
            self.token_usage.append((current_time, tokens))
            self.tpm_window_tokens += tokens
        
        # Increment request counter for RPM window
        self.rpm_window_requests += 1
        
        # Update rate calculations
        self._calculate_rates()
    
    def get_current_rates(self):
        """
        Get current rate information for monitoring.
        
        Returns:
            dict: Dictionary with current rate information
        """
        self._refresh_windows()
        self._calculate_rates()
        
        # Get the window-adjusted rates (scaled to minute for UI consistency)
        window_rpm, window_tpm = self._calculate_window_rates()
        
        rpm_window_max_requests, tpm_window_max_tokens = self._calculate_window_limits()
        
        return {
            'rpm': int(self.current_rpm),            # Standard RPM - requests in last minute
            'tpm': int(self.current_tpm),            # Standard TPM - tokens in last minute
            'max_rpm': self.max_rpm,
            'max_tpm': self.max_tpm,
            'rpm_window_size': self.rpm_window_size,
            'tpm_window_size': self.tpm_window_size,
            'rpm_window_requests': self.rpm_window_requests,
            'tpm_window_tokens': self.tpm_window_tokens,
            'rpm_window_max_requests': rpm_window_max_requests,
            'tpm_window_max_tokens': tpm_window_max_tokens,
            'rpm_window_start_time': self.rpm_window_start_time,
            'tpm_window_start_time': self.tpm_window_start_time,
            'window_rpm': int(window_rpm),           # Window-scaled RPM
            'window_tpm': int(window_tpm)            # Window-scaled TPM
        }
    
    def reset(self):
        """Reset the internal state of the rate limiter."""
        self.request_timestamps.clear()
        self.token_usage.clear()
        self.rpm_window_start_time = time.time()
        self.tpm_window_start_time = time.time()
        self.rpm_window_requests = 0
        self.tpm_window_tokens = 0
        self.current_rpm = 0
        self.current_tpm = 0

