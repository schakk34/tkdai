window.addEventListener('DOMContentLoaded', () => {
    const rhythm = new Rhythm(
        document.getElementById('rhythmTimeline'),
        document.getElementById('durationSlider'),
        document.getElementById('playbackIndicator'),
        document.getElementById('markerList'),
        document.getElementById('duration'),
        document.getElementById('countdown')
    );
    const loaded = localStorage.getItem('loadedRhythm');
    if (loaded) {
        const { title, markers } = JSON.parse(loaded);
        rhythm.loadSavedRhythm(markers);
        localStorage.removeItem('loadedRhythm');
    }
});

class Rhythm {
    constructor(timelineElement, durationSlider, playbackIndicator, markerList, durationDisplay, countdownElement) {
        this.timelineElement = timelineElement;
        this.durationSlider = durationSlider;
        this.playbackIndicator = playbackIndicator;
        this.markerList = markerList;
        this.durationDisplay = durationDisplay;
        this.countdownElement = countdownElement;
        this.markers = [];
        this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        this.isPlaying = false;
        this.suppressNextClick = false;
        this.scheduledOscillators = [];
        this.bindEvents();
    }

    bindEvents() {
        this.timelineElement.addEventListener('click', (e) => this.handleTimelineClick(e));

        document.getElementById('playBtn').addEventListener('click', () => this.play());
        document.getElementById('stopBtn').addEventListener('click', () => this.stop());
        document.getElementById('saveBtn').addEventListener('click', () => this.save());
        document.getElementById('clearBtn').addEventListener('click', () => this.clear());

        document.querySelectorAll('.template-card').forEach(card => {
            card.addEventListener('click', () => this.loadTemplate(card.dataset.template));
        });
        this.durationSlider.addEventListener('input', () => this.durationSliderChange());
    }

    handleTimelineClick(event) {
        if (this.suppressNextClick) {
            this.suppressNextClick = false;
            return;
        }
        const rect = this.timelineElement.getBoundingClientRect();
        const x = event.clientX - rect.left;
        const maxDuration = parseFloat(this.durationSlider.value);
        const time = (x / rect.width) * maxDuration;
        const marker = this.addMarker(time, x);
        this.timelineElement.appendChild(marker);
        this.markers.push(marker);
        this.updateMarkerList();
    }

    addMarker(time, left) {
        const marker = document.createElement('div');
        marker.className = 'rhythm-marker';
        marker.dataset.time = time;
        marker.style.left = `${left}px`;
        this.handleMarkerEvents(marker);
        return marker;
    }

    handleMarkerEvents(marker) {
        let isDragging = false;
        let startX = 0;
        let startLeft = 0;
        let hasMoved = false;

        const onMouseDown = (e) => {
            isDragging = true;
            hasMoved = false;
            startX = e.clientX;
            startLeft = parseFloat(marker.style.left) || 0;
            e.stopPropagation();
        };

        const onMouseMove = (e) => {
            if (!isDragging) return;

            const deltaX = e.clientX - startX;
            if (Math.abs(deltaX) > 3) hasMoved = true; // movement threshold to detect dragging

            const rect = this.timelineElement.getBoundingClientRect();
            let newLeft = Math.max(0, Math.min(startLeft + deltaX, rect.width));
            marker.style.left = `${newLeft}px`;

            const maxDuration = parseFloat(this.durationSlider.value);
            marker.dataset.time = (newLeft / rect.width) * maxDuration;

            this.updateMarkerList();
        };

        const onMouseUp = () => {
            if (isDragging) {
                isDragging = false;
                if (hasMoved) this.suppressNextClick = true;
                this.durationSliderChange();
            }
        };

        const onClick = (e) => {
            if (!hasMoved) {
                e.stopPropagation();
                this.timelineElement.removeChild(marker);
                this.markers = this.markers.filter(m => m !== marker);
                this.durationSliderChange();
                this.updateMarkerList();
            }
        };

        marker.addEventListener('mousedown', onMouseDown);
        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
        marker.addEventListener('click', onClick)
    }

    updateMarkerList() {
        this.markerList.innerHTML = '';
        this.markers.sort((a, b) => parseFloat(a.dataset.time) - parseFloat(b.dataset.time))
            .forEach((marker, index) => {
                const item = document.createElement('div');
                item.className = 'marker-item';
                item.innerHTML = `
                    <span>Marker ${index + 1}</span>
                    <span class="marker-time">${this.formatTime(parseFloat(marker.dataset.time))}</span>
                `;
                this.markerList.appendChild(item);
            });
    }

    formatTime(seconds) {
        const minutes = Math.floor(seconds / 60);
        const secs = seconds % 60;
        const ms = Math.floor((secs % 1) * 1000);
        return `${minutes}:${Math.floor(secs).toString().padStart(2, '0')}.${ms.toString().padStart(3, '0')}`;
    }

    durationSliderChange() {
        this.durationDisplay.textContent = this.formatTime(this.durationSlider.value);
        this.updateMarkersPosition();
    }

    updateMarkersPosition() {
        const maxDuration = parseFloat(this.durationSlider.value);
        const rect = this.timelineElement.getBoundingClientRect();
        this.markers.forEach(marker => {
            const time = parseFloat(marker.dataset.time);
            marker.style.left = `${(time / maxDuration) * rect.width}px`;
        });
        this.updateMarkerList();
    }

    play() {
        if (this.isPlaying) this.stop();
        this.countdownElement.style.display = 'block';
        let count = 3;
        this.countdownElement.textContent = count;
        const countdown = setInterval(() => {
            count--;
            if (count > 0) {
                this.countdownElement.textContent = count;
            } else {
                clearInterval(countdown);
                this.countdownElement.style.display = 'none';
                this.startPlayback();
            }
        }, 1000);
    }

    startPlayback() {
        this.stop();
        this.isPlaying = true;

        const duration = parseFloat(this.durationSlider.value);
        const startTime = this.audioContext.currentTime;
        const sorted = [...this.markers].sort((a, b) => parseFloat(a.dataset.time) - parseFloat(b.dataset.time));

        sorted.forEach(marker => {
            const markerTime = parseFloat(marker.dataset.time);
            const clickTime = startTime + markerTime;
            this.scheduleClickSound(clickTime);
        });

        // Animate indicator
        this.animatePlaybackIndicator(startTime, duration);

        // Repeat
        this.loopTimeout = setTimeout(() => {
            if (this.isPlaying) this.startPlayback(); // seamless loop
        }, duration * 1000);
    }

    animatePlaybackIndicator(startTime, duration) {
        const indicator = this.playbackIndicator;
        const timelineWidth = this.timelineElement.offsetWidth;

        const animate = () => {
            if (!this.isPlaying) return;
            const now = this.audioContext.currentTime;
            const elapsed = (now - startTime) % duration;

            const progress = elapsed / duration;
            indicator.style.left = `${progress * timelineWidth}px`;

            requestAnimationFrame(animate);
        };

        requestAnimationFrame(animate);
    }

    scheduleClickSound(timeInFuture) {
        const osc = this.audioContext.createOscillator();
        const gain = this.audioContext.createGain();

        osc.type = 'sine';
        osc.frequency.setValueAtTime(1000, timeInFuture);
        gain.gain.setValueAtTime(0.1, timeInFuture);

        osc.connect(gain);
        gain.connect(this.audioContext.destination);

        osc.start(timeInFuture);
        osc.stop(timeInFuture + 0.05);

        this.scheduledOscillators.push(osc);
    }

    stop() {
        this.isPlaying = false;
        clearTimeout(this.loopTimeout);
        this.scheduledOscillators.forEach(osc => {
            try { osc.stop(); } catch (_) {}
        });
        this.scheduledOscillators = [];
        this.playbackIndicator.style.left = '0px';
    }

    save() {
        this.stop();

        const duration = parseFloat(this.durationSlider.value);
        const markers = this.markers
            .map(marker => parseFloat(marker.dataset.time))
            .sort((a, b) => a - b);

        const title = prompt("Enter a title for your rhythm:");
        if (!title) return;

        const data = {
            type: 'rhythm',
            title: title,
            description: `Saved rhythm with ${markers.length} markers`,
            file_path: '',  // optional if you have a real audio file
            duration: duration,
            markers: markers,
        };

        fetch('/library/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        })
        .then(res => res.json())
        .then(response => {
            if (response.success) {
                alert('Rhythm saved to your library!');
            } else {
                alert(`Failed to save: ${response.error}`);
            }
        })
        .catch(err => {
            console.error('Save error:', err);
            alert('Something went wrong saving your rhythm.');
        });
    }

    clear() {
        this.stop();
        this.markers.forEach(marker => marker.remove());
        this.markers = [];
        this.durationSliderChange();
        this.updateMarkerList();
    }

    loadTemplate(template) {
        const templates = {
            whiteBelt: [7.5, [0, 1.5, 3, 4.5, 6, 7.5]],
            blackBelt: [9, [0, 1, 2.5, 3.5, 5, 6.5, 8, 9]],
            customChoreo: [5, [0, 0.5, 1.5, 2, 3, 3.5, 4.5, 5]]
        };
        if (!(template in templates)) return;
        this.clear();
        const set = templates[template]
        const maxDuration = set[0] > parseFloat(this.durationSlider.max) ? parseFloat(this.durationSlider.max) : set[0];
        this.durationSlider.value = maxDuration
        const rect = this.timelineElement.getBoundingClientRect();
        set[1].forEach(time => {
            const left = (time / maxDuration) * rect.width;
            const marker = this.addMarker(time, left);
            this.timelineElement.appendChild(marker);
            this.markers.push(marker);
        });
        this.durationSliderChange();
        this.updateMarkerList();
    }

    loadSavedRhythm(markers) {
        this.clear();
        const duration = Math.max(...markers) + 1;
        this.durationSlider.value = duration;
        const rect = this.timelineElement.getBoundingClientRect();
        markers.forEach(time => {
            const left = (time / duration) * rect.width;
            const marker = this.addMarker(time, left);
            this.timelineElement.appendChild(marker);
            this.markers.push(marker);
        });
        this.durationSliderChange();
        this.updateMarkerList();
    }

}