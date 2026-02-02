"""
Advanced orchestrator for disposable compute platform with VM and GPU support
"""
import asyncio
import docker
import libvirt
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import subprocess
import os

from src.models.pod import Pod, PodSpec, PodStatus, PodType, GPUResource, ResourceRequirements
from src.models.vm import VM, VMSpec, VMStatus, VMType, VMDisk, VMNetworkInterface, Hypervisor
from src.models.gpu import GPUDevice, GPUStatus, GPUAllocation, GPUConfiguration
from src.containers.orchestrator import ContainerOrchestrator


class VMOrchestrator:
    """Manages VM lifecycle for disposable environments"""

    def __init__(self, hypervisor_uri: str = "qemu:///system"):
        self.hypervisor_uri = hypervisor_uri
        self.conn = None
        self.logger = logging.getLogger(__name__)
        self._connect_hypervisor()

    def _connect_hypervisor(self):
        """Connect to the hypervisor"""
        try:
            self.conn = libvirt.open(self.hypervisor_uri)
            if self.conn is None:
                raise Exception(f"Failed to connect to hypervisor at {self.hypervisor_uri}")
        except Exception as e:
            self.logger.error(f"Error connecting to hypervisor: {e}")
            raise

    def create_vm(self, vm_spec: VMSpec, vm_disk_path: str) -> str:
        """Create a VM based on the specification"""
        try:
            # Define the VM XML configuration
            vm_xml = self._generate_vm_xml(vm_spec, vm_disk_path)
            
            # Create the VM
            dom = self.conn.defineXML(vm_xml)
            if dom is None:
                raise Exception("Failed to define VM")
                
            # Start the VM
            if dom.create() < 0:
                raise Exception("Failed to start VM")
                
            return dom.UUIDString()
        except Exception as e:
            self.logger.error(f"Failed to create VM: {e}")
            raise

    def _generate_vm_xml(self, vm_spec: VMSpec, vm_disk_path: str) -> str:
        """Generate libvirt XML for VM configuration"""
        # This is a simplified XML template - in practice, this would be more complex
        xml_template = f"""<domain type='kvm'>
  <name>{vm_spec.base_image.replace(':', '_').replace('/', '_')}_vm_{datetime.now().strftime('%Y%m%d_%H%M%S')}</name>
  <memory unit='MiB'>{vm_spec.memory_mb}</memory>
  <currentMemory unit='MiB'>{vm_spec.memory_mb}</currentMemory>
  <vcpu placement='static'>{vm_spec.cpu_cores}</vcpu>
  <os>
    <type arch='x86_64' machine='pc-q35-6.2'>hvm</type>
  </os>
  <features>
    <acpi/>
    <apic/>
  </features>
  <cpu mode='host-model' check='partial'/>
  <clock offset='utc'>
    <timer name='rtc' tickpolicy='catchup'/>
    <timer name='pit' tickpolicy='delay'/>
    <timer name='hpet' present='no'/>
  </clock>
  <on_poweroff>destroy</on_poweroff>
  <on_reboot>restart</on_reboot>
  <on_crash>destroy</on_crash>
  <pm>
    <suspend-to-mem enabled='no'/>
    <suspend-to-disk enabled='no'/>
  </pm>
  <devices>
    <emulator>/usr/bin/qemu-system-x86_64</emulator>
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2' cache='none'/>
      <source file='{vm_disk_path}'/>
      <target dev='vda' bus='virtio'/>
      <address type='pci' domain='0x0000' bus='0x04' slot='0x00' function='0x0'/>
    </disk>
    <interface type='bridge'>
      <source bridge='virbr0'/>
      <model type='virtio'/>
      <address type='pci' domain='0x0000' bus='0x01' slot='0x00' function='0x0'/>
    </interface>
"""

        # Add GPU passthrough if requested
        if vm_spec.gpu_passthrough:
            # In a real implementation, we would discover actual GPU PCI addresses
            # For now, we'll add a placeholder that would be replaced with real addresses
            xml_template += """    <hostdev mode='subsystem' type='pci' managed='yes'>
      <source>
        <address domain='0x0000' bus='0x01' slot='0x00' function='0x0'/>
      </source>
      <address type='pci' domain='0x0000' bus='0x05' slot='0x00' function='0x0'/>
    </hostdev>
"""

        xml_template += """    <serial type='pty'>
      <target type='isa-serial' port='0'>
        <model name='isa-serial'/>
      </target>
    </serial>
    <console type='pty'>
      <target type='serial' port='0'/>
    </console>
    <input type='tablet' bus='usb'>
      <address type='usb' bus='0' port='1'/>
    </input>
    <input type='mouse' bus='ps2'/>
    <input type='keyboard' bus='ps2'/>
    <graphics type='spice' autoport='yes'>
      <listen type='address' address='0.0.0.0'/>
    </graphics>
    <video>
      <model type='qxl' ram='65536' vram='65536' vgamem='16384' heads='1' primary='yes'/>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x01' function='0x0'/>
    </video>
    <memballoon model='virtio'>
      <address type='pci' domain='0x0000' bus='0x02' slot='0x00' function='0x0'/>
    </memballoon>
  </devices>
</domain>"""

        return xml_template

    def start_vm(self, vm_id: str):
        """Start a VM"""
        try:
            dom = self.conn.lookupByUUIDString(vm_id)
            dom.create()
        except Exception as e:
            self.logger.error(f"Failed to start VM {vm_id}: {e}")
            raise

    def stop_vm(self, vm_id: str):
        """Stop a VM"""
        try:
            dom = self.conn.lookupByUUIDString(vm_id)
            dom.shutdown()
        except Exception as e:
            self.logger.error(f"Failed to stop VM {vm_id}: {e}")
            raise

    def destroy_vm(self, vm_id: str):
        """Destroy a VM completely"""
        try:
            dom = self.conn.lookupByUUIDString(vm_id)
            if dom.isActive():
                dom.destroy()  # Force shutdown if running
            dom.undefine()
        except Exception as e:
            self.logger.error(f"Failed to destroy VM {vm_id}: {e}")
            raise

    def get_vm_status(self, vm_id: str) -> VMStatus:
        """Get the status of a VM"""
        try:
            dom = self.conn.lookupByUUIDString(vm_id)
            state, _ = dom.state()
            
            # Libvirt states: 0=VIR_DOMAIN_NOSTATE, 1=VIR_DOMAIN_RUNNING, 2=VIR_DOMAIN_BLOCKED,
            # 3=VIR_DOMAIN_PAUSED, 4=VIR_DOMAIN_SHUTDOWN, 5=VIR_DOMAIN_SHUTOFF, 6=VIR_DOMAIN_CRASHED, 7=VIR_DOMAIN_PMSUSPENDED
            state_map = {
                1: VMStatus.RUNNING,
                3: VMStatus.PAUSED,
                5: VMStatus.STOPPED,
                6: VMStatus.ERROR
            }
            
            return state_map.get(state, VMStatus.ERROR)
        except libvirt.libvirtError:
            return VMStatus.ERROR

    def create_vm_disk(self, base_image: str, size_gb: int) -> str:
        """Create a VM disk from a base image"""
        # Create a unique disk path
        disk_path = f"/var/lib/libvirt/images/dcp-vm-disk-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{os.urandom(4).hex()}.qcow2"
        
        try:
            # Create a qcow2 disk image based on the base image
            cmd = ["qemu-img", "create", "-f", "qcow2", "-b", base_image, disk_path, f"{size_gb}G"]
            subprocess.run(cmd, check=True)
            return disk_path
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to create VM disk: {e}")
            raise


class GPUManager:
    """Manages GPU resources for disposable environments"""

    def __init__(self):
        self.gpu_devices: Dict[str, GPUDevice] = {}
        self.allocations: Dict[str, GPUAllocation] = {}
        self.logger = logging.getLogger(__name__)
        self._discover_gpus()

    def _discover_gpus(self):
        """Discover available GPUs on the system"""
        try:
            # This is a simplified discovery - in practice, this would interface with nvidia-smi or similar
            # For now, we'll simulate discovering some GPUs

            # Check if nvidia-smi is available (NVIDIA GPUs)
            result = subprocess.run(['which', 'nvidia-smi'], capture_output=True, text=True)
            if result.returncode == 0:
                # Query NVIDIA GPUs
                cmd = ["nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,utilization.gpu,temperature.gpu,power.draw", "--format=csv,noheader,nounits"]
                result = subprocess.run(cmd, capture_output=True, text=True)

                if result.returncode == 0:
                    for i, line in enumerate(result.stdout.strip().split('\n')):
                        if line.strip():
                            values = [val.strip() for val in line.split(',')]
                            if len(values) >= 7:
                                idx, name, mem_total, mem_used, util, temp, power = values

                                # Create GPU spec based on the discovered GPU
                                from src.models.gpu import GPUSpec, GPUVendor, GPUFamily

                                # Determine vendor and family from the name
                                vendor = GPUVendor.NVIDIA
                                family = GPUFamily.GEFORCE  # Default, could be more specific

                                if "Tesla" in name:
                                    family = GPUFamily.TESLA
                                elif "Quadro" in name:
                                    family = GPUFamily.QUADRO
                                elif "A100" in name:
                                    family = GPUFamily.A100
                                elif "H100" in name:
                                    family = GPUFamily.H100
                                elif "V100" in name:
                                    family = GPUFamily.V100

                                gpu_spec = GPUSpec(
                                    vendor=vendor,
                                    family=family,
                                    model=name.strip(),
                                    memory_mb=int(mem_total),
                                    cuda_cores=None  # Would need additional query
                                )

                                gpu_device = GPUDevice(
                                    id=f"gpu-nvidia-{idx}",
                                    spec=gpu_spec,
                                    status=GPUStatus.AVAILABLE,
                                    node_id="local-node",
                                    driver_version="unknown",
                                    memory_total_mb=int(mem_total),
                                    memory_used_mb=int(mem_used),
                                    utilization_percent=float(util),
                                    temperature_celsius=float(temp) if temp != "" else None,
                                    power_draw_watts=float(power) if power != "" else None
                                )

                                self.gpu_devices[gpu_device.id] = gpu_device
        except Exception as e:
            self.logger.warning(f"Could not discover GPUs: {e}")

    def allocate_gpus(self, gpu_req: GPUResource, pod_id: str) -> List[GPUAllocation]:
        """Allocate GPU resources to a pod"""
        allocations = []

        # Find available GPUs matching the requirements
        available_gpus = []
        for gpu in self.gpu_devices.values():
            if gpu.status == GPUStatus.AVAILABLE and gpu.spec:
                # Check if GPU family matches (with compatibility mapping)
                if self._gpu_compatible(gpu, gpu_req):
                    available_gpus.append(gpu)

        # Take only as many as requested
        selected_gpus = available_gpus[:gpu_req.count]

        if len(selected_gpus) < gpu_req.count:
            available_count = len(selected_gpus)
            raise Exception(f"Not enough compatible GPUs available. Requested: {gpu_req.count}, Available: {available_count}")

        for gpu in selected_gpus:
            # Mark GPU as allocated
            gpu.status = GPUStatus.ALLOCATED
            gpu.allocated_to_pod = pod_id

            # Create allocation record
            alloc = GPUAllocation(
                id=f"alloc-{pod_id}-{gpu.id}",
                pod_id=pod_id,
                gpu_device_id=gpu.id,
                allocation_time=datetime.now()
            )

            allocations.append(alloc)
            self.allocations[alloc.id] = alloc

        return allocations

    def _gpu_compatible(self, gpu: GPUDevice, gpu_req: GPUResource) -> bool:
        """Check if a GPU is compatible with the requirements"""
        if not gpu.spec:
            return False

        # Exact match
        if gpu.spec.family == gpu_req.gpu_type:
            return True

        # Compatibility mappings
        if gpu_req.gpu_type == GPUFamily.NVIDIA_TESLA:
            return gpu.spec.family in [GPUFamily.TESLA, GPUFamily.A100, GPUFamily.H100, GPUFamily.V100]
        elif gpu_req.gpu_type == GPUFamily.NVIDIA_A100:
            return gpu.spec.family == GPUFamily.A100
        elif gpu_req.gpu_type == GPUFamily.NVIDIA_H100:
            return gpu.spec.family == GPUFamily.H100
        elif gpu_req.gpu_type == GPUFamily.NVIDIA_V100:
            return gpu.spec.family == GPUFamily.V100

        return False

    def release_gpus(self, pod_id: str):
        """Release GPU resources allocated to a pod"""
        # Find allocations for this pod
        pod_allocations = [
            alloc_id for alloc_id, alloc in self.allocations.items()
            if alloc.pod_id == pod_id and alloc.status == "active"
        ]
        
        for alloc_id in pod_allocations:
            alloc = self.allocations[alloc_id]
            
            # Mark GPU as available
            if alloc.gpu_device_id in self.gpu_devices:
                gpu = self.gpu_devices[alloc.gpu_device_id]
                gpu.status = GPUStatus.AVAILABLE
                gpu.allocated_to_pod = None
            
            # Mark allocation as released
            alloc.status = "released"
            alloc.release_time = datetime.now()
    
    def get_gpu_status(self) -> Dict[str, Any]:
        """Get overall GPU status"""
        total_gpus = len(self.gpu_devices)
        available_gpus = len([g for g in self.gpu_devices.values() if g.status == GPUStatus.AVAILABLE])
        allocated_gpus = total_gpus - available_gpus
        
        return {
            "total_gpus": total_gpus,
            "available_gpus": available_gpus,
            "allocated_gpus": allocated_gpus,
            "devices": {gpu_id: {
                "status": gpu.status.value,
                "memory_total_mb": gpu.memory_total_mb,
                "memory_used_mb": gpu.memory_used_mb,
                "utilization_percent": gpu.utilization_percent,
                "allocated_to_pod": gpu.allocated_to_pod
            } for gpu_id, gpu in self.gpu_devices.items()}
        }


class AdvancedOrchestrator:
    """Main orchestrator that handles both containers and VMs with GPU support"""

    def __init__(self):
        self.container_orchestrator = ContainerOrchestrator()
        self.vm_orchestrator = VMOrchestrator()
        self.gpu_manager = GPUManager()
        self.pods: Dict[str, Pod] = {}
        self.logger = logging.getLogger(__name__)

    async def create_pod(self, pod_spec: PodSpec) -> str:
        """Create a pod based on its specification"""
        pod_id = f"pod-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{os.urandom(4).hex()}"
        
        pod = Pod(
            id=pod_id,
            spec=pod_spec,
            status=PodStatus.PROVISIONING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            expires_at=datetime.now() + timedelta(minutes=60)  # Default 1 hour TTL
        )
        
        try:
            if pod_spec.pod_type == PodType.CONTAINER:
                await self._create_container_pod(pod)
            elif pod_spec.pod_type == PodType.VM:
                await self._create_vm_pod(pod)
            elif pod_spec.pod_type == PodType.HYBRID:
                await self._create_hybrid_pod(pod)
            
            pod.status = PodStatus.RUNNING
            pod.updated_at = datetime.now()
            
        except Exception as e:
            pod.status = PodStatus.FAILED
            pod.failure_reason = str(e)
            pod.updated_at = datetime.now()
            raise
        
        self.pods[pod_id] = pod
        return pod_id

    async def _create_container_pod(self, pod: Pod):
        """Create a container-based pod"""
        # Allocate GPUs if required
        if pod.spec.gpu_required and pod.spec.gpu_config:
            gpu_allocations = self.gpu_manager.allocate_gpus(pod.spec.gpu_config, pod.id)
            pod.metadata['gpu_allocations'] = [alloc.id for alloc in gpu_allocations]
        
        # Use the existing container orchestrator
        from src.containers.orchestrator import ContainerConfig
        config = ContainerConfig(
            image=pod.spec.image,
            command=' '.join(pod.spec.command) if pod.spec.command else None,
            environment=pod.spec.environment,
            ports={f"{port}/tcp": None for port in pod.spec.ports} if pod.spec.ports else {},
            volumes=pod.spec.volumes,
            resource_limits={
                'mem_limit': f"{pod.spec.resource_requirements.memory_mb}m",
                'cpu_quota': int(pod.spec.resource_requirements.cpu_cores * 100000)  # Convert to microseconds
            } if pod.spec.resource_requirements else {}
        )
        
        container_id = self.container_orchestrator.create_container(config)
        pod.container_id = container_id

    async def _create_vm_pod(self, pod: Pod):
        """Create a VM-based pod"""
        vm_id = None
        vm_disk_path = None

        try:
            # Allocate GPUs if required
            gpu_allocations = []
            if pod.spec.gpu_required and pod.spec.gpu_config:
                gpu_allocations = self.gpu_manager.allocate_gpus(pod.spec.gpu_config, pod.id)
                pod.metadata['gpu_allocations'] = [alloc.id for alloc in gpu_allocations]

            # Create VM disk
            vm_disk_path = self.vm_orchestrator.create_vm_disk(
                pod.spec.image,
                pod.spec.resource_requirements.storage_gb
            )
            pod.vm_disk_path = vm_disk_path

            # Create VM specification
            vm_spec = VMSpec(
                vm_type=VMType.LINUX if 'linux' in pod.spec.app_type.lower() else VMType.WINDOWS,
                base_image=pod.spec.image,
                cpu_cores=int(pod.spec.resource_requirements.cpu_cores),
                memory_mb=pod.spec.resource_requirements.memory_mb,
                disk_size_gb=pod.spec.resource_requirements.storage_gb,
                gpu_passthrough=bool(pod.spec.gpu_required),
                gpu_config=pod.spec.gpu_config.__dict__ if pod.spec.gpu_config else None
            )

            # Create and start VM
            vm_id = self.vm_orchestrator.create_vm(vm_spec, vm_disk_path)
            pod.vm_id = vm_id

        except Exception as e:
            # If anything fails, clean up allocated resources
            if vm_id:
                try:
                    self.vm_orchestrator.destroy_vm(vm_id)
                except Exception as cleanup_error:
                    self.logger.error(f"Error cleaning up VM during creation failure: {cleanup_error}")

            if vm_disk_path and os.path.exists(vm_disk_path):
                try:
                    os.remove(vm_disk_path)
                except OSError as cleanup_error:
                    self.logger.error(f"Error removing VM disk during creation failure: {cleanup_error}")

            if gpu_allocations:
                try:
                    self.gpu_manager.release_gpus(pod.id)
                except Exception as cleanup_error:
                    self.logger.error(f"Error releasing GPUs during creation failure: {cleanup_error}")

            raise

    async def _create_hybrid_pod(self, pod: Pod):
        """Create a hybrid pod with both containers and VMs"""
        # For now, implement as a VM with container-like features
        await self._create_vm_pod(pod)

    async def start_pod(self, pod_id: str):
        """Start a pod"""
        if pod_id not in self.pods:
            raise ValueError(f"Pod {pod_id} not found")
        
        pod = self.pods[pod_id]
        
        if pod.spec.pod_type in [PodType.VM, PodType.HYBRID]:
            if pod.vm_id:
                self.vm_orchestrator.start_vm(pod.vm_id)
        else:  # Container
            if pod.container_id:
                self.container_orchestrator.start_container(pod.container_id)
        
        pod.status = PodStatus.RUNNING
        pod.updated_at = datetime.now()

    async def stop_pod(self, pod_id: str):
        """Stop a pod"""
        if pod_id not in self.pods:
            raise ValueError(f"Pod {pod_id} not found")
        
        pod = self.pods[pod_id]
        
        if pod.spec.pod_type in [PodType.VM, PodType.HYBRID]:
            if pod.vm_id:
                self.vm_orchestrator.stop_vm(pod.vm_id)
        else:  # Container
            if pod.container_id:
                self.container_orchestrator.stop_container(pod.container_id)
        
        pod.status = PodStatus.STOPPED
        pod.updated_at = datetime.now()

    async def destroy_pod(self, pod_id: str):
        """Destroy a pod and all its resources"""
        if pod_id not in self.pods:
            raise ValueError(f"Pod {pod_id} not found")

        pod = self.pods[pod_id]

        try:
            # Stop the pod if running
            if pod.status in [PodStatus.RUNNING, PodStatus.STARTING]:
                try:
                    await self.stop_pod(pod_id)
                except Exception as e:
                    self.logger.warning(f"Error stopping pod {pod_id} before destruction: {e}")

            # Release GPU allocations
            if 'gpu_allocations' in pod.metadata:
                try:
                    self.gpu_manager.release_gpus(pod_id)
                except Exception as e:
                    self.logger.warning(f"Error releasing GPU allocations for pod {pod_id}: {e}")

            # Clean up resources based on pod type
            if pod.spec.pod_type in [PodType.VM, PodType.HYBRID]:
                # Clean up VM resources
                if pod.vm_id:
                    try:
                        self.vm_orchestrator.destroy_vm(pod.vm_id)
                    except Exception as e:
                        self.logger.warning(f"Error destroying VM for pod {pod_id}: {e}")

                # Clean up VM disk
                if pod.vm_disk_path and os.path.exists(pod.vm_disk_path):
                    try:
                        os.remove(pod.vm_disk_path)
                    except OSError as e:
                        self.logger.warning(f"Could not remove VM disk {pod.vm_disk_path}: {e}")
            else:  # Container
                # Clean up container resources
                if pod.container_id:
                    try:
                        self.container_orchestrator.remove_container(pod.container_id)
                    except Exception as e:
                        self.logger.warning(f"Error removing container for pod {pod_id}: {e}")

        except Exception as e:
            # Even if cleanup fails, update pod status to terminated
            self.logger.error(f"Error during pod {pod_id} destruction: {e}")
            pod.status = PodStatus.ERROR
            pod.failure_reason = str(e)
            pod.updated_at = datetime.now()
            raise
        else:
            # Update pod status only if everything succeeded
            pod.status = PodStatus.TERMINATED
            pod.updated_at = datetime.now()

    async def get_pod_status(self, pod_id: str) -> PodStatus:
        """Get the status of a pod"""
        if pod_id not in self.pods:
            raise ValueError(f"Pod {pod_id} not found")
        
        pod = self.pods[pod_id]
        
        if pod.spec.pod_type in [PodType.VM, PodType.HYBRID]:
            if pod.vm_id:
                return self._map_vm_status_to_pod_status(
                    self.vm_orchestrator.get_vm_status(pod.vm_id)
                )
        else:  # Container
            # For containers, we'd need to check the container status
            # This is a simplified implementation
            pass
        
        return pod.status

    def _map_vm_status_to_pod_status(self, vm_status: VMStatus) -> PodStatus:
        """Map VM status to Pod status"""
        mapping = {
            VMStatus.RUNNING: PodStatus.RUNNING,
            VMStatus.STOPPED: PodStatus.STOPPED,
            VMStatus.PAUSED: PodStatus.STOPPED,
            VMStatus.SUSPENDED: PodStatus.STOPPED,
            VMStatus.ERROR: PodStatus.FAILED
        }
        return mapping.get(vm_status, PodStatus.FAILED)

    def get_gpu_status(self) -> Dict[str, Any]:
        """Get GPU status across the platform"""
        return self.gpu_manager.get_gpu_status()