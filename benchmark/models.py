"""
QEdge Profiler Model Registry
ONNX model definitions and backend detection.
"""

import os
from typing import Dict, List, Optional
from dataclasses import dataclass

try:
    import onnxruntime as ort
    ONNXRUNTIME_AVAILABLE = True
except ImportError:
    ONNXRUNTIME_AVAILABLE = False
    print("[ModelRegistry] Warning: onnxruntime not installed")


@dataclass
class ModelInfo:
    """Model metadata."""
    name: str
    path: str
    input_shape: tuple
    input_name: str
    output_name: str
    precisions: List[str]
    description: str


class ModelRegistry:
    """Registry of available ONNX models."""

    # Base path for ONNX models
    MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'models', 'onnx')

    # Model definitions
    MODELS = {
        'MobileNetV2': ModelInfo(
            name='MobileNetV2',
            path='mobilenetv2-7.onnx',
            input_shape=(1, 3, 224, 224),
            input_name='input',
            output_name='output',
            precisions=['FP32', 'FP16'],
            description='Efficient CNN for image classification (3.5M params)'
        ),
        'MobileNetV3-Small': ModelInfo(
            name='MobileNetV3-Small',
            path='mobilenetv3-small-1.0.onnx',
            input_shape=(1, 3, 224, 224),
            input_name='input',
            output_name='output',
            precisions=['FP32'],
            description='Ultra-efficient CNN for mobile devices (2.5M params)'
        ),
        'ResNet50': ModelInfo(
            name='ResNet50',
            path='resnet50-v2-7.onnx',
            input_shape=(1, 3, 224, 224),
            input_name='data',
            output_name='resnetv24_dense0_fwd',
            precisions=['FP32', 'FP16'],
            description='Deep residual network for image classification (25M params)'
        ),
        'EfficientNet-Lite0': ModelInfo(
            name='EfficientNet-Lite0',
            path='efficientnet-lite0.onnx',
            input_shape=(1, 3, 224, 224),
            input_name='images:0',
            output_name='Softmax:0',
            precisions=['FP32'],
            description='Balanced efficiency and accuracy (4.7M params)'
        ),
        'SqueezeNet': ModelInfo(
            name='SqueezeNet',
            path='squeezenet1.1-7.onnx',
            input_shape=(1, 3, 224, 224),
            input_name='data',
            output_name='squeezenet0_flatten0_reshape0',
            precisions=['FP32'],
            description='Extremely compact CNN (1.2M params)'
        )
    }

    @classmethod
    def get_model(cls, name: str) -> Optional[ModelInfo]:
        """Get model info by name."""
        return cls.MODELS.get(name)

    @classmethod
    def list_models(cls) -> List[ModelInfo]:
        """List all available models."""
        return list(cls.MODELS.values())

    @classmethod
    def get_model_path(cls, name: str) -> Optional[str]:
        """Get full path to model file."""
        model_info = cls.get_model(name)
        if not model_info:
            return None

        full_path = os.path.join(cls.MODEL_DIR, model_info.path)

        # Check if file exists
        if os.path.exists(full_path):
            return full_path

        return None

    @classmethod
    def check_model_availability(cls) -> Dict[str, bool]:
        """Check which models are available locally."""
        availability = {}

        for name, info in cls.MODELS.items():
            full_path = os.path.join(cls.MODEL_DIR, info.path)
            availability[name] = os.path.exists(full_path)

        return availability

    @classmethod
    def get_available_models(cls) -> List[str]:
        """Get list of models that exist on disk."""
        available = []

        for name in cls.MODELS.keys():
            if cls.get_model_path(name):
                available.append(name)

        return available


class BackendDetector:
    """Detect available ONNX Runtime execution providers."""

    @staticmethod
    def get_available_providers() -> List[str]:
        """Get list of available ONNX Runtime providers."""
        if not ONNXRUNTIME_AVAILABLE:
            return []

        try:
            return ort.get_available_providers()
        except Exception as e:
            print(f"[BackendDetector] Error getting providers: {e}")
            return []

    @staticmethod
    def get_backend_mapping() -> Dict[str, List[str]]:
        """Map backend names to ONNX Runtime provider names."""
        return {
            'CPU': ['CPUExecutionProvider'],
            'GPU': ['CUDAExecutionProvider', 'ROCMExecutionProvider', 'DmlExecutionProvider'],
            'NPU': ['QNNExecutionProvider', 'CoreMLExecutionProvider', 'OpenVINOExecutionProvider']
        }

    @classmethod
    def detect_available_backends(cls) -> Dict[str, bool]:
        """Detect which backends (CPU/GPU/NPU) are available."""
        available_providers = cls.get_available_providers()
        backend_mapping = cls.get_backend_mapping()

        backends = {}

        for backend_name, provider_names in backend_mapping.items():
            # Check if any provider for this backend is available
            backends[backend_name] = any(
                provider in available_providers for provider in provider_names
            )

        return backends

    @classmethod
    def get_providers_for_backend(cls, backend: str) -> List[str]:
        """
        Get ONNX Runtime provider list for a backend.

        Args:
            backend: 'CPU', 'GPU', or 'NPU'

        Returns:
            List of provider names with CPU fallback
        """
        backend_mapping = cls.get_backend_mapping()
        available_providers = cls.get_available_providers()

        if backend not in backend_mapping:
            return ['CPUExecutionProvider']

        # Get providers for this backend
        backend_providers = backend_mapping[backend]

        # Filter to only available providers
        selected_providers = [
            p for p in backend_providers if p in available_providers
        ]

        # Always add CPU as fallback
        if 'CPUExecutionProvider' not in selected_providers:
            selected_providers.append('CPUExecutionProvider')

        return selected_providers

    @classmethod
    def get_provider_info(cls, provider_name: str) -> Dict[str, str]:
        """Get human-readable info about a provider."""
        provider_info = {
            'CPUExecutionProvider': {
                'name': 'CPU',
                'description': 'CPU-based inference (universal)',
                'icon': '💻'
            },
            'CUDAExecutionProvider': {
                'name': 'CUDA GPU',
                'description': 'NVIDIA GPU acceleration',
                'icon': '🎮'
            },
            'ROCMExecutionProvider': {
                'name': 'ROCm GPU',
                'description': 'AMD GPU acceleration',
                'icon': '🎮'
            },
            'DmlExecutionProvider': {
                'name': 'DirectML',
                'description': 'Windows DirectX GPU acceleration',
                'icon': '🪟'
            },
            'QNNExecutionProvider': {
                'name': 'Qualcomm NPU',
                'description': 'Qualcomm Neural Processing Unit',
                'icon': '🧠'
            },
            'CoreMLExecutionProvider': {
                'name': 'Apple Neural Engine',
                'description': 'Apple Silicon NPU',
                'icon': '🍎'
            },
            'OpenVINOExecutionProvider': {
                'name': 'Intel OpenVINO',
                'description': 'Intel Neural Compute Stick / iGPU',
                'icon': '⚡'
            }
        }

        return provider_info.get(provider_name, {
            'name': provider_name,
            'description': 'Unknown provider',
            'icon': '❓'
        })


def get_system_info() -> Dict:
    """Get comprehensive system and ONNX Runtime info."""
    detector = BackendDetector()

    available_providers = detector.get_available_providers()
    available_backends = detector.detect_available_backends()
    model_availability = ModelRegistry.check_model_availability()
    available_models = ModelRegistry.get_available_models()

    return {
        'onnxruntime_available': ONNXRUNTIME_AVAILABLE,
        'onnxruntime_version': ort.__version__ if ONNXRUNTIME_AVAILABLE else None,
        'available_providers': available_providers,
        'available_backends': available_backends,
        'provider_details': [
            detector.get_provider_info(p) for p in available_providers
        ],
        'models': {
            'total': len(ModelRegistry.MODELS),
            'available': len(available_models),
            'list': available_models,
            'availability': model_availability
        }
    }


# Quick test function
if __name__ == '__main__':
    print("="*60)
    print("QEdge Profiler - Model Registry & Backend Detection")
    print("="*60)

    info = get_system_info()

    print(f"\nONNX Runtime: {'✓ Available' if info['onnxruntime_available'] else '✗ Not installed'}")
    if info['onnxruntime_version']:
        print(f"Version: {info['onnxruntime_version']}")

    print("\nAvailable Backends:")
    for backend, available in info['available_backends'].items():
        status = '✓' if available else '✗'
        print(f"  {status} {backend}")

    print("\nExecution Providers:")
    for provider_detail in info['provider_details']:
        print(f"  {provider_detail['icon']} {provider_detail['name']} - {provider_detail['description']}")

    print(f"\nModels: {info['models']['available']}/{info['models']['total']} available")
    for model_name, available in info['models']['availability'].items():
        status = '✓' if available else '✗'
        print(f"  {status} {model_name}")
