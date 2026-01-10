"""
Streaming module for GUI applications in disposable compute platform
"""
import asyncio
import logging
import websockets
import json
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from dataclasses import dataclass
import subprocess
import os
import threading
import queue


@dataclass
class StreamSession:
    """Represents a streaming session for a GUI application"""
    id: str
    pod_id: str
    client_connection: Optional[str] = None  # WebSocket connection identifier
    stream_type: str = "webrtc"  # webrtc, vnc, rdp, etc.
    status: str = "initializing"
    created_at: datetime = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    bandwidth_kbps: int = 10000  # 10 Mbps default
    resolution: str = "1920x1080"
    fps: int = 30
    codec: str = "h264"
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


@dataclass
class StreamMetrics:
    """Metrics for a streaming session"""
    session_id: str
    timestamp: datetime
    frame_rate: float
    latency_ms: float
    bandwidth_kbps: float
    packet_loss_rate: float
    resolution: str
    cpu_usage: float
    memory_usage: float
    gpu_usage: Optional[float] = None


class StreamEncoder:
    """Handles video encoding for GUI streaming"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.encoding_processes: Dict[str, subprocess.Popen] = {}
    
    async def start_encoding(self, session_id: str, input_source: str, output_destination: str, 
                           resolution: str = "1920x1080", fps: int = 30, codec: str = "h264"):
        """Start video encoding process"""
        try:
            # Construct FFmpeg command for encoding
            cmd = [
                "ffmpeg",
                "-f", "x11grab",  # For Linux X11
                "-video_size", resolution,
                "-framerate", str(fps),
                "-i", input_source,  # e.g., :0.0+0,0 for X11 display
                "-c:v", codec,
                "-preset", "ultrafast",  # Optimize for low latency
                "-tune", "zerolatency",
                "-b:v", "8M",  # Bitrate
                "-maxrate", "8M",
                "-bufsize", "16M",
                "-g", str(fps * 2),  # GOP size
                "-keyint_min", str(fps),
                "-pix_fmt", "yuv420p",
                "-f", "webm",  # Output format for WebRTC
                "-deadline", "realtime",
                "-cpu-used", "8",
                output_destination
            ]
            
            # Start the encoding process
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.encoding_processes[session_id] = proc
            
            self.logger.info(f"Started encoding for session {session_id}")
            
        except Exception as e:
            self.logger.error(f"Failed to start encoding for session {session_id}: {e}")
            raise
    
    async def stop_encoding(self, session_id: str):
        """Stop video encoding process"""
        if session_id in self.encoding_processes:
            proc = self.encoding_processes[session_id]
            proc.terminate()
            try:
                proc.wait(timeout=5)  # Wait up to 5 seconds for graceful shutdown
            except subprocess.TimeoutExpired:
                proc.kill()  # Force kill if it doesn't shut down gracefully
            
            del self.encoding_processes[session_id]
            self.logger.info(f"Stopped encoding for session {session_id}")
    
    async def restart_encoding(self, session_id: str, input_source: str, output_destination: str,
                            resolution: str, fps: int, codec: str):
        """Restart video encoding with new parameters"""
        await self.stop_encoding(session_id)
        await self.start_encoding(session_id, input_source, output_destination, resolution, fps, codec)


class StreamDecoder:
    """Handles video decoding for GUI streaming"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.decoding_processes: Dict[str, subprocess.Popen] = {}
    
    async def start_decoding(self, session_id: str, input_source: str, output_destination: str):
        """Start video decoding process"""
        try:
            # Construct FFmpeg command for decoding
            cmd = [
                "ffmpeg",
                "-i", input_source,
                "-c:v", "libvpx-vp9",  # Assuming VP9 input for WebRTC
                output_destination
            ]
            
            # Start the decoding process
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.decoding_processes[session_id] = proc
            
            self.logger.info(f"Started decoding for session {session_id}")
            
        except Exception as e:
            self.logger.error(f"Failed to start decoding for session {session_id}: {e}")
            raise
    
    async def stop_decoding(self, session_id: str):
        """Stop video decoding process"""
        if session_id in self.decoding_processes:
            proc = self.decoding_processes[session_id]
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            
            del self.decoding_processes[session_id]
            self.logger.info(f"Stopped decoding for session {session_id}")


class InputHandler:
    """Handles input events from the client and forwards to the GUI application"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.input_queues: Dict[str, queue.Queue] = {}
    
    def initialize_input_queue(self, session_id: str):
        """Initialize input queue for a session"""
        self.input_queues[session_id] = queue.Queue(maxsize=100)  # Limit queue size
    
    def handle_client_input(self, session_id: str, input_event: Dict[str, Any]):
        """Handle input event from client"""
        if session_id not in self.input_queues:
            self.logger.warning(f"No input queue for session {session_id}")
            return
        
        try:
            # Put the input event in the queue for processing
            self.input_queues[session_id].put_nowait(input_event)
            self.logger.debug(f"Queued input event for session {session_id}: {input_event['type']}")
        except queue.Full:
            self.logger.warning(f"Input queue full for session {session_id}, dropping event")
    
    def process_input_events(self, session_id: str, pod_display: str = ":0"):
        """Process input events and forward to the GUI application"""
        if session_id not in self.input_queues:
            return
        
        input_queue = self.input_queues[session_id]
        
        while not input_queue.empty():
            try:
                event = input_queue.get_nowait()
                
                # Forward the event to the GUI application
                # This is a simplified implementation - in reality, you'd use xdotool, wmctrl, etc.
                if event['type'] == 'mouse_move':
                    self._simulate_mouse_move(event, pod_display)
                elif event['type'] == 'mouse_click':
                    self._simulate_mouse_click(event, pod_display)
                elif event['type'] == 'keyboard':
                    self._simulate_keyboard_input(event, pod_display)
                elif event['type'] == 'resize':
                    self._handle_resize(event, pod_display)
                
            except queue.Empty:
                break
    
    def _simulate_mouse_move(self, event: Dict[str, Any], pod_display: str):
        """Simulate mouse movement"""
        # In a real implementation, this would use xdotool or similar
        # Example: xdotool mousemove --display :0 100 200
        x, y = event['x'], event['y']
        cmd = ["xdotool", "mousemove", "--display", pod_display, str(x), str(y)]
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to move mouse: {e}")
    
    def _simulate_mouse_click(self, event: Dict[str, Any], pod_display: str):
        """Simulate mouse click"""
        button = event.get('button', '1')  # Default to left click
        cmd = ["xdotool", "click", "--display", pod_display, button]
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to click mouse: {e}")
    
    def _simulate_keyboard_input(self, event: Dict[str, Any], pod_display: str):
        """Simulate keyboard input"""
        key = event.get('key', '')
        cmd = ["xdotool", "key", "--delay", "0", "--display", pod_display, key]
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to press key: {e}")
    
    def _handle_resize(self, event: Dict[str, Any], pod_display: str):
        """Handle window resize event"""
        width, height = event['width'], event['height']
        # In a real implementation, this would resize the display
        # This is typically handled at the X11/virtual display level
        self.logger.info(f"Resize event: {width}x{height} for display {pod_display}")


class StreamServer:
    """Main streaming server that manages GUI application streams"""
    
    def __init__(self):
        self.sessions: Dict[str, StreamSession] = {}
        self.stream_encoder = StreamEncoder()
        self.stream_decoder = StreamDecoder()
        self.input_handler = InputHandler()
        self.logger = logging.getLogger(__name__)
        self.websocket_servers = []
        self.metrics_history: Dict[str, List[StreamMetrics]] = {}
    
    async def start_stream_session(self, pod_id: str, stream_type: str = "webrtc", 
                                 resolution: str = "1920x1080", fps: int = 30) -> str:
        """Start a new streaming session for a pod"""
        session_id = f"stream-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{os.urandom(4).hex()}"
        
        session = StreamSession(
            id=session_id,
            pod_id=pod_id,
            stream_type=stream_type,
            resolution=resolution,
            fps=fps,
            status="initializing"
        )
        
        self.sessions[session_id] = session
        self.input_handler.initialize_input_queue(session_id)
        
        try:
            # Set up the streaming pipeline
            await self._setup_streaming_pipeline(session)
            
            session.status = "active"
            session.started_at = datetime.now()
            
            self.logger.info(f"Started streaming session {session_id} for pod {pod_id}")
            
            # Start metrics collection
            asyncio.create_task(self._collect_metrics(session_id))
            
            return session_id
            
        except Exception as e:
            session.status = "error"
            self.logger.error(f"Failed to start streaming session {session_id}: {e}")
            raise
    
    async def _setup_streaming_pipeline(self, session: StreamSession):
        """Set up the streaming pipeline for a session"""
        # Determine the input source (this would be the pod's display)
        input_source = f"{session.pod_id}_display"  # Placeholder
        
        # Set up output destination (this would be the WebRTC stream endpoint)
        output_destination = f"stream_{session.id}.webm"  # Placeholder
        
        # Start encoding
        await self.stream_encoder.start_encoding(
            session.id,
            input_source,
            output_destination,
            session.resolution,
            session.fps
        )
    
    async def stop_stream_session(self, session_id: str):
        """Stop a streaming session"""
        if session_id not in self.sessions:
            self.logger.error(f"Session {session_id} not found")
            return
        
        session = self.sessions[session_id]
        session.status = "stopping"
        
        # Stop encoding
        await self.stream_encoder.stop_encoding(session_id)
        
        # Stop decoding if applicable
        await self.stream_decoder.stop_decoding(session_id)
        
        # Clean up input queue
        if session_id in self.input_handler.input_queues:
            del self.input_handler.input_queues[session_id]
        
        session.status = "stopped"
        session.ended_at = datetime.now()
        
        self.logger.info(f"Stopped streaming session {session_id}")
    
    async def handle_client_input(self, session_id: str, input_event: Dict[str, Any]):
        """Handle input from a client"""
        if session_id not in self.sessions:
            self.logger.error(f"Session {session_id} not found for input handling")
            return
        
        # Process the input event
        self.input_handler.handle_client_input(session_id, input_event)
        
        # Forward to the appropriate pod
        session = self.sessions[session_id]
        # Process inputs in a separate thread to avoid blocking
        threading.Thread(
            target=self.input_handler.process_input_events,
            args=(session_id, f"{session.pod_id}_display"),
            daemon=True
        ).start()
    
    async def _collect_metrics(self, session_id: str):
        """Collect metrics for a streaming session"""
        while session_id in self.sessions:
            session = self.sessions[session_id]
            if session.status != "active":
                break
            
            # Collect metrics (this is a simplified implementation)
            metrics = StreamMetrics(
                session_id=session_id,
                timestamp=datetime.now(),
                frame_rate=session.fps,
                latency_ms=50,  # Placeholder
                bandwidth_kbps=session.bandwidth_kbps,
                packet_loss_rate=0.0,  # Placeholder
                resolution=session.resolution,
                cpu_usage=25.0,  # Placeholder
                memory_usage=50.0,  # Placeholder
                gpu_usage=30.0  # Placeholder
            )
            
            # Store metrics
            if session_id not in self.metrics_history:
                self.metrics_history[session_id] = []
            self.metrics_history[session_id].append(metrics)
            
            # Keep only the last 100 metrics to prevent memory issues
            if len(self.metrics_history[session_id]) > 100:
                self.metrics_history[session_id] = self.metrics_history[session_id][-100:]
            
            # Wait before collecting next metrics
            await asyncio.sleep(1)
    
    def get_session_metrics(self, session_id: str) -> List[StreamMetrics]:
        """Get metrics for a session"""
        return self.metrics_history.get(session_id, [])
    
    def get_active_sessions(self) -> List[StreamSession]:
        """Get all active streaming sessions"""
        return [session for session in self.sessions.values() if session.status == "active"]
    
    async def start_websocket_server(self, host: str = "0.0.0.0", port: int = 8765):
        """Start the WebSocket server for streaming"""
        async def handler(websocket, path):
            # Extract session ID from path
            path_parts = path.strip('/').split('/')
            if len(path_parts) < 2 or path_parts[0] != 'stream':
                await websocket.close(code=1008, reason="Invalid path")
                return
            
            session_id = path_parts[1]
            if session_id not in self.sessions:
                await websocket.close(code=1008, reason="Session not found")
                return
            
            session = self.sessions[session_id]
            session.client_connection = str(websocket.remote_address)
            
            try:
                async for message in websocket:
                    # Handle incoming messages (input events, control messages)
                    try:
                        data = json.loads(message)
                        
                        if data.get('type') == 'input':
                            await self.handle_client_input(session_id, data.get('event', {}))
                        elif data.get('type') == 'control':
                            # Handle control messages like resize, quality adjustment
                            await self._handle_control_message(session_id, data)
                        else:
                            self.logger.warning(f"Unknown message type: {data.get('type')}")
                            
                    except json.JSONDecodeError:
                        self.logger.error(f"Invalid JSON received from session {session_id}")
                    except Exception as e:
                        self.logger.error(f"Error handling message from session {session_id}: {e}")
                        
            except websockets.exceptions.ConnectionClosed:
                self.logger.info(f"Client disconnected from session {session_id}")
            except Exception as e:
                self.logger.error(f"Error in WebSocket handler for session {session_id}: {e}")
            finally:
                # Clean up when connection closes
                if session_id in self.sessions:
                    session = self.sessions[session_id]
                    session.client_connection = None
                    self.logger.info(f"Cleaned up connection for session {session_id}")
        
        server = await websockets.serve(handler, host, port)
        self.websocket_servers.append(server)
        
        self.logger.info(f"Started WebSocket streaming server on {host}:{port}")
        
        return server
    
    async def _handle_control_message(self, session_id: str, control_data: Dict[str, Any]):
        """Handle control messages like resize, quality adjustment"""
        if session_id not in self.sessions:
            return
        
        session = self.sessions[session_id]
        control_type = control_data.get('subtype')
        
        if control_type == 'resize':
            new_resolution = control_data.get('resolution')
            if new_resolution:
                session.resolution = new_resolution
                # In a real implementation, we'd adjust the encoder settings
                self.logger.info(f"Adjusted resolution for session {session_id} to {new_resolution}")
        
        elif control_type == 'quality':
            new_quality = control_data.get('quality')  # e.g., 'low', 'medium', 'high'
            if new_quality:
                # Adjust encoding parameters based on quality setting
                self.logger.info(f"Adjusted quality for session {session_id} to {new_quality}")
    
    async def cleanup_stale_sessions(self):
        """Clean up stale or inactive streaming sessions"""
        current_time = datetime.now()
        sessions_to_remove = []
        
        for session_id, session in self.sessions.items():
            # If session has been in 'initializing' state for more than 5 minutes, remove it
            if (session.status == "initializing" and 
                current_time - session.created_at > timedelta(minutes=5)):
                sessions_to_remove.append(session_id)
            # If session has been in 'error' state for more than 1 minute, remove it
            elif (session.status == "error" and 
                  current_time - session.created_at > timedelta(minutes=1)):
                sessions_to_remove.append(session_id)
        
        for session_id in sessions_to_remove:
            self.logger.info(f"Cleaning up stale session {session_id}")
            await self.stop_stream_session(session_id)
            del self.sessions[session_id]


class StreamingManager:
    """Main streaming manager that integrates with the rest of the platform"""
    
    def __init__(self):
        self.stream_server = StreamServer()
        self.logger = logging.getLogger(__name__)
        self.streaming_sessions: Dict[str, str] = {}  # pod_id -> session_id
    
    async def initialize(self):
        """Initialize the streaming manager"""
        self.logger.info("Initialized streaming manager")
    
    async def start_pod_streaming(self, pod_id: str, stream_type: str = "webrtc", 
                                resolution: str = "1920x1080", fps: int = 30) -> str:
        """Start streaming for a pod"""
        session_id = await self.stream_server.start_stream_session(
            pod_id, stream_type, resolution, fps
        )
        
        self.streaming_sessions[pod_id] = session_id
        self.logger.info(f"Started streaming for pod {pod_id}, session {session_id}")
        
        return session_id
    
    async def stop_pod_streaming(self, pod_id: str):
        """Stop streaming for a pod"""
        if pod_id not in self.streaming_sessions:
            self.logger.warning(f"No streaming session found for pod {pod_id}")
            return
        
        session_id = self.streaming_sessions[pod_id]
        await self.stream_server.stop_stream_session(session_id)
        
        del self.streaming_sessions[pod_id]
        self.logger.info(f"Stopped streaming for pod {pod_id}")
    
    async def get_stream_url(self, pod_id: str) -> Optional[str]:
        """Get the streaming URL for a pod"""
        if pod_id not in self.streaming_sessions:
            return None
        
        session_id = self.streaming_sessions[pod_id]
        # In a real implementation, this would return an actual streaming URL
        # For now, return a placeholder
        return f"ws://streaming.disposable-platform.com/stream/{session_id}"
    
    def get_streaming_status(self, pod_id: str) -> Dict[str, Any]:
        """Get the streaming status for a pod"""
        if pod_id not in self.streaming_sessions:
            return {"status": "not_streaming"}
        
        session_id = self.streaming_sessions[pod_id]
        if session_id not in self.stream_server.sessions:
            return {"status": "not_found"}
        
        session = self.stream_server.sessions[session_id]
        metrics = self.stream_server.get_session_metrics(session_id)
        
        return {
            "status": session.status,
            "session_id": session_id,
            "stream_type": session.stream_type,
            "resolution": session.resolution,
            "fps": session.fps,
            "client_connected": session.client_connection is not None,
            "created_at": session.created_at.isoformat(),
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "recent_metrics": [
                {
                    "timestamp": m.timestamp.isoformat(),
                    "frame_rate": m.frame_rate,
                    "latency_ms": m.latency_ms,
                    "bandwidth_kbps": m.bandwidth_kbps
                }
                for m in metrics[-5:]  # Last 5 metrics
            ] if metrics else []
        }
    
    async def start_global_streaming_server(self, host: str = "0.0.0.0", port: int = 8765):
        """Start the global streaming server"""
        return await self.stream_server.start_websocket_server(host, port)
    
    async def cleanup_inactive_streams(self):
        """Clean up inactive streaming sessions"""
        await self.stream_server.cleanup_stale_sessions()