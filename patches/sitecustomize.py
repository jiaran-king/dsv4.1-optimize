"""Resolve the selected Host VMM modules from this overlay."""

import importlib.abc
import importlib.util
from pathlib import Path
import sys


class VmmBackport(importlib.abc.MetaPathFinder):
    root = Path(__file__).resolve().parents[1]
    modules = {
        "vllm_ascend.device.hardware_profile",
        "vllm_ascend.models.deepseek_v41.engram.embedding",
        "vllm_ascend.models.deepseek_v41.engram.local_shared_vmm",
        "vllm_ascend.models.deepseek_v41.engram.local_vmm_host",
        "vllm_ascend.models.deepseek_v41.model",
        "vllm_ascend.worker.worker",
    }

    def find_spec(self, fullname, path=None, target=None):
        if fullname in self.modules:
            source = self.root.joinpath(*fullname.split(".")).with_suffix(".py")
            return importlib.util.spec_from_file_location(fullname, source)
        return None


sys.meta_path.insert(0, VmmBackport())
