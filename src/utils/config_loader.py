import yaml
from pathlib import Path
from typing import Any, Dict

class ConfigLoader:
    _instance = None
    _config = None
    
    def __new__(cls):
        """单例模式，确保配置只加载一次"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._config is None:
            self._load_config()
    
    def _load_config(self):
        """加载配置文件"""
        # 获取项目根目录
        project_root = Path(__file__).parent.parent.parent
        config_path = project_root / 'config' / 'config.yaml'
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                self._config = self._process_paths(config)
        except FileNotFoundError:
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
        except yaml.YAMLError as e:
            raise ValueError(f"YAML格式错误: {e}")
    
    def _process_paths(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """处理路径配置"""
        if 'paths' in config and 'project_root' in config['paths']:
            project_root = Path(config['paths']['project_root'])
            
            # 将相对路径转换为绝对路径
            for key, path in config['paths'].items():
                if key != 'project_root' and not Path(path).is_absolute():
                    config['paths'][key] = str(project_root / path)
        
        return config

    def get(self, key_path, default=None):
        """获取配置值，支持嵌套键"""
        keys = key_path.split('.')
        value = self._config
        
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
                if value is None:
                    return default
            else:
                return default
        return value
    
    def __getitem__(self, key_path):
        return self.get(key_path)
    
    @property
    def all(self):
        """获取所有配置"""
        return self._config

# 创建全局配置实例
config = ConfigLoader()