import asyncio
import logging
import websockets
import json
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass
from datetime import datetime
import cv2
import numpy as np
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from aiortc.contrib.media import MediaBlackhole, MediaPlayer, MediaRecorder

from ..types.config import settings
from ..networking.network_manager import NetworkManager


@dataclass
class StreamSession:
    pod_id: str
    connection: RTCPeerConnection
    client_ip: str
    started_at: datetime
    last_activity: datetime
    video_track: Optional[VideoStreamTrack] = None
    audio_track: Optional[Any] = None


class StreamingAgent:
    """Streaming agent for WebRTC-based desktop application streaming"""
    
    def __init__(self, pod_id: str, network_manager: NetworkManager):
        self.pod_id = pod_id
        self.network_manager = network_manager
        self.sessions: Dict[str, StreamSession] = {}
        self.running = False
        self.video_capture = None
        self.input_queue = asyncio.Queue()
        
        # Initialize video capture for the pod
        # In a real implementation, this would capture from the pod's display
        try:
            # For now, we'll use a mock video capture
            # In a real system, this would capture from the pod's framebuffer
            pass
        except Exception as e:
            logging.error(f"Error initializing video capture: {e}")
    
    async def start_streaming_server(self, port: int):
        """Start the WebRTC streaming server"""
        try:
            # In a real implementation, this would start a WebRTC server
            # For now, we'll just log that it's starting
            logging.info(f"Starting streaming server for pod {self.pod_id} on port {port}")
            
            # Set up WebRTC peer connection
            pc = RTCPeerConnection()
            
            # In a real implementation, you would set up data channels for input
            # and video/audio tracks for output
            
            self.running = True
            logging.info(f"Streaming server started for pod {self.pod_id}")
            
        except Exception as e:
            logging.error(f"Error starting streaming server: {e}")
    
    async def stop_streaming_server(self):
        """Stop the WebRTC streaming server"""
        try:
            self.running = False
            
            # Close all active sessions
            for session_id, session in list(self.sessions.items()):
                await self.close_session(session_id)
            
            # Release video capture
            if self.video_capture:
                self.video_capture.release()
            
            logging.info(f"Streaming server stopped for pod {self.pod_id}")
        except Exception as e:
            logging.error(f"Error stopping streaming server: {e}")
    
    async def create_session(self, client_ip: str) -> Optional[str]:
        """Create a new streaming session"""
        try:
            session_id = f"session-{self.pod_id}-{int(datetime.now().timestamp())}"
            
            # Create WebRTC peer connection
            pc = RTCPeerConnection()
            
            # Create session object
            session = StreamSession(
                pod_id=self.pod_id,
                connection=pc,
                client_ip=client_ip,
                started_at=datetime.now(),
                last_activity=datetime.now()
            )
            
            self.sessions[session_id] = session
            
            # Set up event handlers
            @pc.on("iceconnectionstatechange")
            async def on_iceconnectionstatechange():
                logging.info(f"ICE connection state for session {session_id}: {pc.iceConnectionState}")
                if pc.iceConnectionState == "failed":
                    await self.close_session(session_id)
            
            logging.info(f"Created streaming session {session_id} for pod {self.pod_id}")
            return session_id
            
        except Exception as e:
            logging.error(f"Error creating streaming session: {e}")
            return None
    
    async def close_session(self, session_id: str):
        """Close a streaming session"""
        if session_id in self.sessions:
            session = self.sessions[session_id]
            try:
                await session.connection.close()
            except:
                pass  # Connection might already be closed
            del self.sessions[session_id]
            logging.info(f"Closed streaming session {session_id}")
    
    async def handle_client_offer(self, session_id: str, offer: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle a WebRTC offer from a client"""
        try:
            if session_id not in self.sessions:
                return None
            
            session = self.sessions[session_id]
            
            # Set remote description
            offer_desc = RTCSessionDescription(sdp=offer["sdp"], type=offer["type"])
            await session.connection.setRemoteDescription(offer_desc)
            
            # Create video track for the pod
            # In a real implementation, this would capture from the pod's display
            video_track = PodVideoStreamTrack(self.pod_id)
            session.connection.addTrack(video_track)
            session.video_track = video_track
            
            # Create answer
            answer = await session.connection.createAnswer()
            await session.connection.setLocalDescription(answer)
            
            return {
                "sdp": session.connection.localDescription.sdp,
                "type": session.connection.localDescription.type
            }
            
        except Exception as e:
            logging.error(f"Error handling client offer: {e}")
            return None
    
    async def send_input_to_pod(self, session_id: str, input_data: Dict[str, Any]):
        """Send input data (mouse, keyboard) to the pod"""
        try:
            if session_id not in self.sessions:
                return
            
            # Add input to queue for processing
            await self.input_queue.put({
                "session_id": session_id,
                "input_data": input_data,
                "timestamp": datetime.now()
            })
            
            # In a real implementation, this would send the input to the pod
            logging.debug(f"Input sent to pod {self.pod_id}: {input_data}")
            
        except Exception as e:
            logging.error(f"Error sending input to pod: {e}")
    
    async def process_input_queue(self):
        """Process the input queue and send inputs to pods"""
        while self.running:
            try:
                input_item = await asyncio.wait_for(self.input_queue.get(), timeout=1.0)
                
                # Process input for the specific pod
                await self._send_input_to_pod_backend(
                    input_item["session_id"],
                    input_item["input_data"]
                )
                
            except asyncio.TimeoutError:
                # No input in queue, continue
                continue
            except Exception as e:
                logging.error(f"Error processing input queue: {e}")
    
    async def _send_input_to_pod_backend(self, session_id: str, input_data: Dict[str, Any]):
        """Send input to the actual pod backend (container/VM)"""
        try:
            # This is where you would send the input to the actual pod
            # For containers: send to X11 server or input device
            # For VMs: send via QEMU monitor or guest agent
            session = self.sessions.get(session_id)
            if not session:
                return
            
            # Mock implementation - in reality, this would interface with
            # the container/VM to inject the input
            logging.debug(f"Sending input to pod backend: {input_data}")
            
        except Exception as e:
            logging.error(f"Error sending input to pod backend: {e}")
    
    def get_session_stats(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get statistics for a streaming session"""
        if session_id not in self.sessions:
            return None
        
        session = self.sessions[session_id]
        duration = datetime.now() - session.started_at
        
        return {
            "pod_id": self.pod_id,
            "session_id": session_id,
            "client_ip": session.client_ip,
            "duration": duration.total_seconds(),
            "connected_at": session.started_at.isoformat(),
            "last_activity": session.last_activity.isoformat(),
            "active_streams": {
                "video": session.video_track is not None,
                "audio": session.audio_track is not None
            }
        }
    
    def get_all_session_stats(self) -> Dict[str, Any]:
        """Get statistics for all streaming sessions"""
        stats = {
            "pod_id": self.pod_id,
            "active_sessions": len(self.sessions),
            "sessions": {}
        }
        
        for session_id, session in self.sessions.items():
            stats["sessions"][session_id] = self.get_session_stats(session_id)
        
        return stats


class PodVideoStreamTrack(VideoStreamTrack):
    """Video stream track that captures from a pod's display"""
    
    def __init__(self, pod_id: str):
        super().__init__()  # Don't forget to call the base constructor!
        self.pod_id = pod_id
        self.kind = "video"
        
        # In a real implementation, this would connect to the pod's display
        # For now, we'll generate a mock video stream
        self.frame_count = 0
    
    async def recv(self):
        """Receive the next video frame"""
        try:
            # In a real implementation, this would capture from the pod's display
            # For now, we'll generate a mock frame
            self.frame_count += 1
            
            # Create a mock frame (in reality, this would come from pod display)
            frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            
            # Add some mock content to make it visible
            cv2.putText(
                frame, 
                f"Pod: {self.pod_id} - Frame: {self.frame_count}", 
                (50, 50), 
                cv2.FONT_HERSHEY_SIMPLEX, 
                1, 
                (255, 255, 255), 
                2
            )
            
            # Convert to the format expected by aiortc
            from av import VideoFrame
            new_frame = VideoFrame.from_ndarray(frame, format="bgr24")
            new_frame.pts = self.frame_count
            new_frame.time_base = 1/30  # 30fps
            
            return new_frame
            
        except Exception as e:
            logging.error(f"Error capturing frame: {e}")
            # Return a blank frame in case of error
            frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            from av import VideoFrame
            new_frame = VideoFrame.from_ndarray(frame, format="bgr24")
            new_frame.pts = self.frame_count
            new_frame.time_base = 1/30
            return new_frame


class StreamingManager:
    """Manager for all streaming agents"""
    
    def __init__(self):
        self.streaming_agents: Dict[str, StreamingAgent] = {}
        self.network_manager = NetworkManager()
    
    async def create_streaming_agent(self, pod_id: str) -> Optional[StreamingAgent]:
        """Create a streaming agent for a pod"""
        try:
            if pod_id in self.streaming_agents:
                return self.streaming_agents[pod_id]
            
            agent = StreamingAgent(pod_id, self.network_manager)
            self.streaming_agents[pod_id] = agent
            
            # Allocate a port for streaming
            streaming_url = await self.network_manager.setup_streaming_endpoint(pod_id)
            if not streaming_url:
                logging.error(f"Could not allocate streaming port for pod {pod_id}")
                del self.streaming_agents[pod_id]
                return None
            
            # Start the streaming server
            port = self._extract_port_from_url(streaming_url)
            await agent.start_streaming_server(port)
            
            return agent
            
        except Exception as e:
            logging.error(f"Error creating streaming agent: {e}")
            return None
    
    def _extract_port_from_url(self, url: str) -> int:
        """Extract port from streaming URL"""
        # Simple extraction - in reality, you'd parse the URL properly
        if ":" in url:
            try:
                port_str = url.split(":")[-1].split("/")[0]
                return int(port_str)
            except:
                return 8000  # default
        return 8000
    
    async def get_streaming_agent(self, pod_id: str) -> Optional[StreamingAgent]:
        """Get an existing streaming agent"""
        return self.streaming_agents.get(pod_id)
    
    async def remove_streaming_agent(self, pod_id: str):
        """Remove a streaming agent"""
        if pod_id in self.streaming_agents:
            agent = self.streaming_agents[pod_id]
            await agent.stop_streaming_server()
            del self.streaming_agents[pod_id]
    
    def get_overall_stats(self) -> Dict[str, Any]:
        """Get overall streaming statistics"""
        total_sessions = 0
        stats = {
            "total_agents": len(self.streaming_agents),
            "total_sessions": 0,
            "agents": {}
        }
        
        for pod_id, agent in self.streaming_agents.items():
            agent_stats = agent.get_all_session_stats()
            stats["agents"][pod_id] = agent_stats
            stats["total_sessions"] += agent_stats["active_sessions"]
        
        return stats