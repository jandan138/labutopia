import numpy as np
from typing import List
from .data_collector import DataCollector

class MockCollector(DataCollector):
    """Mock data collector for testing purposes - implements same interface as DataCollector but does nothing"""
    
    def __init__(self, camera_configs: List[dict], save_dir="output", 
                 max_episodes=10, max_workers=4, compression=None):
        """Initialize the mock data collector
        
        Args:
            camera_configs: List of camera configuration dicts, each containing 'name' key
            save_dir (str): Root directory for saving data (ignored in mock)
            max_episodes (int): Maximum number of episodes to record (ignored in mock)
            max_workers (int): Maximum number of parallel processes (ignored in mock)
            compression: Compression method for image data (ignored in mock)
        """
        self.save_dir = save_dir
        self.max_episodes = max_episodes
        self.compression = compression
        self.episode_count = 0
        self.camera_configs = camera_configs
        self.task_instructions = None
        self.temp_task_properties = {}

    def cache_step(self, camera_images: dict = None, joint_angles: np.ndarray = None, language_instruction=None, *args, **kwargs):
        """Mock cache step - does nothing
        
        Args:
            camera_images: Dict of camera name to RGB image {name: np.ndarray}
            joint_angles: Robot joint angles
        """
        # Do nothing - this is a mock collector
        # Override parent method to not actually cache anything
        pass
        
    def write_cached_data(self, final_joint_positions = None, *args, **kwargs):
        """Mock write cached data - does nothing
        
        Args:
            final_joint_positions: Final joint positions
        """
        # Do nothing - this is a mock collector
        # Override parent method to not actually write anything
        self.episode_count += 1
        pass

    def clear_cache(self, *args, **kwargs):
        """Mock clear cache - does nothing"""
        # Do nothing - this is a mock collector
        # Override parent method to not actually clear anything
        self.episode_count += 1
        pass
        
    def close(self):
        """Mock close - does nothing"""
        # Do nothing - this is a mock collector
        # Override parent method to not actually close anything
        pass
