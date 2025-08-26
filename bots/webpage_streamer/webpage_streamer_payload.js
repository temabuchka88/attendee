const _getUserMedia = navigator.mediaDevices.getUserMedia;



class BotOutputManager {
    constructor() {
        
        // For outputting video
        this.botOutputVideoElement = null;
        this.videoSoundSource = null;
        this.botOutputVideoElementCaptureStream = null;

        // For outputting image
        this.botOutputCanvasElement = null;
        this.botOutputCanvasElementCaptureStream = null;
        this.lastImageBytes = null;
        
        // For outputting audio
        this.audioContextForBotOutput = null;
        this.gainNode = null;
        this.destination = null;
        this.botOutputAudioTrack = null;

        this.specialStream = null;
        this.specialStreamAudioElement = null;
        this.specialStreamSource = null;
        this.specialStreamProcessor = null;
        this.specialStreamAudioContext = null;
    }

    connectVideoSourceToAudioContext() {
        if (this.botOutputVideoElement && this.audioContextForBotOutput && !this.videoSoundSource) {
            this.videoSoundSource = this.audioContextForBotOutput.createMediaElementSource(this.botOutputVideoElement);
            this.videoSoundSource.connect(this.gainNode);
        }
    }

    playSpecialStream(stream) {
        this.specialStream = stream;
        
        // Initialize audio context if needed
        this.initializeBotOutputAudioTrack();
        
        // Remove previous audio element if it exists
        if (this.specialStreamAudioElement) {
            this.specialStreamAudioElement.pause();
            if (this.specialStreamSource) {
                this.specialStreamSource.disconnect();
                this.specialStreamSource = null;
            }
            this.specialStreamAudioElement.remove();
        }
        
        // Create audio element for the stream
        this.specialStreamAudioElement = document.createElement('audio');
        this.specialStreamAudioElement.style.display = 'none';
        this.specialStreamAudioElement.srcObject = stream;
        this.specialStreamAudioElement.autoplay = true;
        this.specialStreamAudioElement.muted = true;
        document.body.appendChild(this.specialStreamAudioElement);
        
        // Use a more modern approach with MediaRecorder
        const audioTrack = stream.getAudioTracks()[0];
        if (audioTrack) {
            // Create a new MediaStream with just the audio track
            const audioStream = new MediaStream([audioTrack]);
            
            // Connect the audio stream directly to our output
            if (this.audioContextForBotOutput) {
                const streamSource = this.audioContextForBotOutput.createMediaStreamSource(audioStream);
                streamSource.connect(this.gainNode);
                
                // Store reference for cleanup
                this.specialStreamSource = streamSource;
            }
            
            console.log("Audio track connected to output");
        } else {
            console.warn("No audio track found in the stream");
        }
        
    }

    playVideo(videoUrl) {
        // If camera or mic are on, turn them off
        turnOffMicAndCamera();

        this.addBotOutputVideoElement(videoUrl);

        // Add event listener to wait until the video starts playing
        this.botOutputVideoElement.addEventListener('playing', () => {
            console.log("Video has started playing, turning on mic and camera");

            this.botOutputVideoElementCaptureStream = this.botOutputVideoElement.captureStream();

            turnOnMicAndCamera();
        }, { once: true });
    }

    isVideoPlaying() {
        return !!this.botOutputVideoElement;
    }

    addBotOutputVideoElement(url) {
        // Disconnect previous video source if it exists
        if (this.videoSoundSource) {
            this.videoSoundSource.disconnect();
            this.videoSoundSource = null;
        }
    
        // Remove any existing video element
        if (this.botOutputVideoElement) {
            this.botOutputVideoElement.remove();
        }
    
        // Create new video element
        this.botOutputVideoElement = document.createElement('video');
        this.botOutputVideoElement.style.display = 'none';
        // If url is a string then do it this way
        if (typeof url === 'string') {
            this.botOutputVideoElement.src = url;
        }
        // If url is a stream then do it this way
        else {
            this.botOutputVideoElement.srcObject = url;
        }
        //this.botOutputVideoElement.crossOrigin = 'anonymous';
        this.botOutputVideoElement.loop = false;
        this.botOutputVideoElement.autoplay = true;
        this.botOutputVideoElement.muted = false;
        // Clean up when video ends
        this.botOutputVideoElement.addEventListener('ended', () => {
            turnOffMicAndCamera();
            if (this.videoSoundSource) {
                this.videoSoundSource.disconnect();
                this.videoSoundSource = null;
            }
            this.botOutputVideoElement.remove();
            this.botOutputVideoElement = null;
            this.botOutputVideoElementCaptureStream = null;

            // If we were displaying an image, turn the camera back on
            if (this.botOutputCanvasElementCaptureStream) {
                this.botOutputCanvasElementCaptureStream = null;
                // Resend last image in 1 second
                if (this.lastImageBytes) {
                    setTimeout(() => {
                        this.displayImage(this.lastImageBytes);
                    }, 1000);
                }
            }
        });
    
        document.body.appendChild(this.botOutputVideoElement);
    }

    displayImage(imageBytes) {
        try {
            // Wait for the image to be loaded onto the canvas
            return this.writeImageToBotOutputCanvas(imageBytes)
                .then(async () => {
                // If the stream is already broadcasting, don't do anything
                if (this.botOutputCanvasElementCaptureStream)
                {
                    console.log("Stream already broadcasting, skipping");
                    return;
                }

                // Now that the image is loaded, capture the stream and turn on camera
                this.lastImageBytes = imageBytes;
                this.botOutputCanvasElementCaptureStream = this.botOutputCanvasElement.captureStream(1);
                await turnOnCamera();
            })
            .catch(error => {
                console.error('Error in botOutputManager.displayImage:', error);
            });
        } catch (error) {
            console.error('Error in botOutputManager.displayImage:', error);
        }
    }

    initializeBotOutputAudioTrack() {
        if (this.botOutputAudioTrack) {
            return;
        }

        // Create AudioContext and nodes
        this.audioContextForBotOutput = new AudioContext();
        this.gainNode = this.audioContextForBotOutput.createGain();
        this.destination = this.audioContextForBotOutput.createMediaStreamDestination();

        // Set initial gain
        this.gainNode.gain.value = 1.0;

        // Connect gain node to both destinations
        this.gainNode.connect(this.destination);
        //this.gainNode.connect(this.audioContextForBotOutput.destination);  // For local monitoring

        this.botOutputAudioTrack = this.destination.stream.getAudioTracks()[0];
        
        // Initialize audio queue for continuous playback
        this.audioQueue = [];
        this.nextPlayTime = 0;
        this.isPlaying = false;
        this.sampleRate = 48000; // Default sample rate
        this.numChannels = 1;    // Default channels
        this.turnOffMicTimeout = null;
    }

    playPCMAudio(pcmData, sampleRate = 48000, numChannels = 1) {
        //turnOnMic();

        // Make sure audio context is initialized
        this.initializeBotOutputAudioTrack();
        
        // Update properties if they've changed
        if (this.sampleRate !== sampleRate || this.numChannels !== numChannels) {
            this.sampleRate = sampleRate;
            this.numChannels = numChannels;
        }
        
        // Convert Int16 PCM data to Float32 with proper scaling
        let audioData;
        if (pcmData instanceof Float32Array) {
            audioData = pcmData;
        } else {
            // Create a Float32Array of the same length
            audioData = new Float32Array(pcmData.length);
            // Scale Int16 values (-32768 to 32767) to Float32 range (-1.0 to 1.0)
            for (let i = 0; i < pcmData.length; i++) {
                // Division by 32768.0 scales the range correctly
                audioData[i] = pcmData[i] / 32768.0;
            }
        }
        
        // Add to queue with timing information
        const chunk = {
            data: audioData,
            duration: audioData.length / (numChannels * sampleRate)
        };
        
        this.audioQueue.push(chunk);
        
        // Start playing if not already
        if (!this.isPlaying) {
            this.processAudioQueue();
        }
    }
    
    processAudioQueue() {
        if (this.audioQueue.length === 0) {
            this.isPlaying = false;

            if (this.turnOffMicTimeout) {
                clearTimeout(this.turnOffMicTimeout);
                this.turnOffMicTimeout = null;
            }
            
            // Delay turning off the mic by 2 second and check if queue is still empty
            this.turnOffMicTimeout = setTimeout(() => {
                // Only turn off mic if the queue is still empty
                if (this.audioQueue.length === 0)
                    turnOffMic();
            }, 2000);
            
            return;
        }
        
        this.isPlaying = true;
        
        // Get current time and next play time
        const currentTime = this.audioContextForBotOutput.currentTime;
        this.nextPlayTime = Math.max(currentTime, this.nextPlayTime);
        
        // Get next chunk
        const chunk = this.audioQueue.shift();
        
        // Create buffer for this chunk
        const audioBuffer = this.audioContextForBotOutput.createBuffer(
            this.numChannels,
            chunk.data.length / this.numChannels,
            this.sampleRate
        );
        
        // Fill the buffer
        if (this.numChannels === 1) {
            const channelData = audioBuffer.getChannelData(0);
            channelData.set(chunk.data);
        } else {
            for (let channel = 0; channel < this.numChannels; channel++) {
                const channelData = audioBuffer.getChannelData(channel);
                for (let i = 0; i < chunk.data.length / this.numChannels; i++) {
                    channelData[i] = chunk.data[i * this.numChannels + channel];
                }
            }
        }
        
        // Create source and schedule it
        const source = this.audioContextForBotOutput.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(this.gainNode);
        
        // Schedule precisely
        source.start(this.nextPlayTime);
        this.nextPlayTime += chunk.duration;
        
        // Schedule the next chunk processing
        const timeUntilNextProcess = (this.nextPlayTime - currentTime) * 1000 * 0.8;
        setTimeout(() => this.processAudioQueue(), Math.max(0, timeUntilNextProcess));
    }
}

const botOutputManager = new BotOutputManager();
window.botOutputManager = botOutputManager;

navigator.mediaDevices.getUserMedia = function(constraints) {
    return _getUserMedia.call(navigator.mediaDevices, constraints)
      .then(originalStream => {
        console.log("Intercepted getUserMedia:", constraints);
  
        // Stop any original tracks so we don't actually capture real mic/cam
        originalStream.getTracks().forEach(t => t.stop());
  
        // Create a new MediaStream to return
        const newStream = new MediaStream();
        

        // Audio sending not supported yet
        
        // If audio is requested, add our fake audio track
        if (constraints.audio) {  // Only create once
            botOutputManager.initializeBotOutputAudioTrack();
            newStream.addTrack(botOutputManager.botOutputAudioTrack);
        } 
  
        return newStream;
      })
      .catch(err => {
        console.error("Error in custom getUserMedia override:", err);
        throw err;
      });
  };


async function startReceivingPumpAudio() { 
    const pc = new RTCPeerConnection();

    // When server sends audio, play it.
    const ms = new MediaStream();
    pc.ontrack = (ev) => {
        ms.addTrack(ev.track);
        botOutputManager.playSpecialStream(ms);
    };

    // We only want to RECEIVE audio
    pc.addTransceiver('audio', { direction: 'recvonly' });

    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);

    const res = await fetch('http://localhost:8000/offer_pump_audio', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ sdp: pc.localDescription.sdp, type: pc.localDescription.type })
    });

    if (!res.ok) {
        const t = await res.text();
        alert('No upstream audio yet (or error): ' + res.status + " " + t);
        return;
    }

    const answer = await res.json();
    await pc.setRemoteDescription(answer);
};

setTimeout(() => {
    startReceivingPumpAudio();
}, 10000);