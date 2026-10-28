// Vehicle Entry JavaScript

const fileInput = document.getElementById('vehicle-image');
const previewContainer = document.getElementById('preview-container');
const imagePreview = document.getElementById('image-preview');
const uploadForm = document.getElementById('upload-form');
const processBtn = document.getElementById('process-btn');
const resultSection = document.getElementById('result-section');
const errorSection = document.getElementById('error-section');
const loadingSection = document.getElementById('loading-section');

// File input change handler
fileInput.addEventListener('change', (e) => {
    const file = e.target.files[0];

    if (file) {
        const reader = new FileReader();

        reader.onload = (e) => {
            imagePreview.src = e.target.result;
            previewContainer.style.display = 'block';
        };

        reader.readAsDataURL(file);
    }
});

// Drag and drop functionality
const fileLabel = document.querySelector('.file-label');

fileLabel.addEventListener('dragover', (e) => {
    e.preventDefault();
    fileLabel.style.borderColor = '#3498db';
    fileLabel.style.background = 'rgba(52, 152, 219, 0.1)';
});

fileLabel.addEventListener('dragleave', (e) => {
    e.preventDefault();
    fileLabel.style.borderColor = '#bdc3c7';
    fileLabel.style.background = 'transparent';
});

fileLabel.addEventListener('drop', (e) => {
    e.preventDefault();
    fileLabel.style.borderColor = '#bdc3c7';
    fileLabel.style.background = 'transparent';

    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith('image/')) {
        fileInput.files = e.dataTransfer.files;

        const reader = new FileReader();
        reader.onload = (e) => {
            imagePreview.src = e.target.result;
            previewContainer.style.display = 'block';
        };
        reader.readAsDataURL(file);
    }
});

// Form submission handler
uploadForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const file = fileInput.files[0];

    if (!file) {
        alert('Please select an image first!');
        return;
    }

    // Show loading
    loadingSection.style.display = 'block';
    resultSection.style.display = 'none';
    errorSection.style.display = 'none';
    processBtn.disabled = true;

    // Create form data
    const formData = new FormData();
    formData.append('image', file);

    try {
        const response = await fetch('/process-vehicle', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        loadingSection.style.display = 'none';
        processBtn.disabled = false;

        if (data.success) {
            // Show success result
            document.getElementById('result-plate').textContent = data.license_plate;
            document.getElementById('result-confidence').textContent = data.confidence + '%';
            document.getElementById('result-slot').textContent = '#' + data.slot_number;
            document.getElementById('result-time').textContent = data.entry_time;

            document.getElementById('result-vehicle-img').src = 'data:image/jpeg;base64,' + data.vehicle_image;
            document.getElementById('result-parking-img').src = 'data:image/jpeg;base64,' + data.parking_image;

            resultSection.style.display = 'block';

            // Scroll to result
            resultSection.scrollIntoView({ behavior: 'smooth' });
        } else {
            // Show error
            document.getElementById('error-message').textContent = data.message;
            errorSection.style.display = 'block';
            errorSection.scrollIntoView({ behavior: 'smooth' });
        }
    } catch (error) {
        loadingSection.style.display = 'none';
        processBtn.disabled = false;

        document.getElementById('error-message').textContent = 'An error occurred while processing the image. Please try again.';
        errorSection.style.display = 'block';
        errorSection.scrollIntoView({ behavior: 'smooth' });
    }
});

function resetForm() {
    uploadForm.reset();
    previewContainer.style.display = 'none';
    resultSection.style.display = 'none';
    errorSection.style.display = 'none';
    window.scrollTo({ top: 0, behavior: 'smooth' });
}
