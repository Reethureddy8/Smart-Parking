// Webcam Capture JavaScript

const webcam = document.getElementById('webcam');
const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');

const startWebcamBtn = document.getElementById('start-webcam');
const captureBtn = document.getElementById('capture-btn');
const retakeBtn = document.getElementById('retake-btn');
const processWebcamBtn = document.getElementById('process-webcam-btn');

const webcamPreview = document.getElementById('webcam-preview');
const capturedImage = document.getElementById('captured-image');

const webcamResult = document.getElementById('webcam-result');
const webcamError = document.getElementById('webcam-error');
const webcamLoading = document.getElementById('webcam-loading');

let stream = null;
let capturedBlob = null;

// Start webcam
startWebcamBtn.addEventListener('click', async () => {
    try {
        stream = await navigator.mediaDevices.getUserMedia({
            video: {
                width: { ideal: 1280 },
                height: { ideal: 720 }
            }
        });

        webcam.srcObject = stream;

        startWebcamBtn.style.display = 'none';
        captureBtn.style.display = 'inline-block';

    } catch (error) {
        alert('Could not access webcam. Please ensure you have granted camera permissions.');
        console.error('Webcam error:', error);
    }
});

// Capture image
captureBtn.addEventListener('click', () => {
    // Set canvas size to match video
    canvas.width = webcam.videoWidth;
    canvas.height = webcam.videoHeight;

    // Draw current frame to canvas
    ctx.drawImage(webcam, 0, 0, canvas.width, canvas.height);

    // Convert canvas to blob
    canvas.toBlob((blob) => {
        capturedBlob = blob;

        // Show preview
        const url = URL.createObjectURL(blob);
        capturedImage.src = url;
        webcamPreview.style.display = 'block';

        // Update buttons
        captureBtn.style.display = 'none';
        retakeBtn.style.display = 'inline-block';
        processWebcamBtn.style.display = 'inline-block';

        // Stop webcam stream
        if (stream) {
            stream.getTracks().forEach(track => track.stop());
        }
        webcam.srcObject = null;

    }, 'image/jpeg', 0.95);
});

// Retake image
retakeBtn.addEventListener('click', async () => {
    webcamPreview.style.display = 'none';
    retakeBtn.style.display = 'none';
    processWebcamBtn.style.display = 'none';

    // Restart webcam
    try {
        stream = await navigator.mediaDevices.getUserMedia({
            video: {
                width: { ideal: 1280 },
                height: { ideal: 720 }
            }
        });

        webcam.srcObject = stream;
        captureBtn.style.display = 'inline-block';

    } catch (error) {
        alert('Could not access webcam.');
        startWebcamBtn.style.display = 'inline-block';
    }
});

// Process captured image
processWebcamBtn.addEventListener('click', async () => {
    if (!capturedBlob) {
        alert('No image captured!');
        return;
    }

    // Show loading
    webcamLoading.style.display = 'block';
    webcamResult.style.display = 'none';
    webcamError.style.display = 'none';
    processWebcamBtn.disabled = true;

    // Create form data
    const formData = new FormData();
    formData.append('image', capturedBlob, 'webcam-capture.jpg');

    try {
        const response = await fetch('/process-vehicle', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        webcamLoading.style.display = 'none';
        processWebcamBtn.disabled = false;

        if (data.success) {
            // Show success result
            document.getElementById('webcam-result-plate').textContent = data.license_plate;
            document.getElementById('webcam-result-confidence').textContent = data.confidence + '%';
            document.getElementById('webcam-result-slot').textContent = '#' + data.slot_number;
            document.getElementById('webcam-result-time').textContent = data.entry_time;

            document.getElementById('webcam-result-vehicle-img').src = 'data:image/jpeg;base64,' + data.vehicle_image;
            document.getElementById('webcam-result-parking-img').src = 'data:image/jpeg;base64,' + data.parking_image;

            webcamResult.style.display = 'block';
            webcamResult.scrollIntoView({ behavior: 'smooth' });
        } else {
            // Show error
            document.getElementById('webcam-error-message').textContent = data.message;
            webcamError.style.display = 'block';
            webcamError.scrollIntoView({ behavior: 'smooth' });
        }
    } catch (error) {
        webcamLoading.style.display = 'none';
        processWebcamBtn.disabled = false;

        document.getElementById('webcam-error-message').textContent = 'An error occurred while processing the image. Please try again.';
        webcamError.style.display = 'block';
        webcamError.scrollIntoView({ behavior: 'smooth' });
    }
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (stream) {
        stream.getTracks().forEach(track => track.stop());
    }
});
