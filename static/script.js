// Basic JavaScript for Petrol Pump Management System
// Handles form validation, calculations, and UI enhancements

document.addEventListener('DOMContentLoaded', function() {
    console.log('Petrol Pump System loaded successfully');
    
    // Auto-format phone input
    const phoneInputs = document.querySelectorAll('input[name="phone"]');
    phoneInputs.forEach(input => {
        input.addEventListener('input', function(e) {
            let value = e.target.value.replace(/\D/g, '');
            if (value.length > 10) value = value.slice(0, 10);
            e.target.value = value;
        });
    });
    
    // Form submit validation
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const phone = form.querySelector('input[name="phone"]');
            if (phone && !/^\d{10}$/.test(phone.value)) {
                e.preventDefault();
                alert('Please enter valid 10-digit phone number');
                return false;
            }
        });
    });
});
