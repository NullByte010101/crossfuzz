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
        paths = config.setdefault('paths', {})
        # project_root 为空时默认为仓库根目录
        project_root = Path(paths.get('project_root') or Path(__file__).parent.parent.parent)
        paths['project_root'] = str(project_root)
        self._project_root = project_root

        # 将相对路径转换为绝对路径
        for key, path in paths.items():
            if key != 'project_root':
                paths[key] = self.resolve(path)

        return config

    def resolve(self, path, base=None):
        """将相对路径解析为绝对路径（默认相对于 project_root）"""
        base = Path(base) if base else self._project_root
        path = Path(path)
        return str(path if path.is_absolute() else base / path)

    def path(self, key_path, base=None):
        """获取路径配置并解析为绝对路径，支持字符串或字符串列表"""
        value = self.get(key_path)
        if value is None:
            raise KeyError(f"配置项不存在: {key_path}")
        if isinstance(value, list):
            return [self.resolve(p, base) for p in value]
        return self.resolve(value, base)

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