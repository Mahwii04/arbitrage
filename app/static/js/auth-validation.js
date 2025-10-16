// app/static/js/auth-validation.js
document.addEventListener('DOMContentLoaded', function() {
    // Real-time username availability check
    const usernameInput = document.getElementById('username');
    if (usernameInput) {
        let usernameTimeout;
        
        usernameInput.addEventListener('input', function() {
            clearTimeout(usernameTimeout);
            const username = this.value.trim();
            
            if (username.length < 3) return;
            
            usernameTimeout = setTimeout(() => {
                fetch('/auth/check-username', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': document.querySelector('[name=csrf_token]').value
                    },
                    body: JSON.stringify({username: username})
                })
                .then(response => response.json())
                .then(data => {
                    const feedback = document.getElementById('username-feedback') || 
                                    createFeedbackElement(usernameInput, 'username-feedback');
                    
                    if (data.available) {
                        feedback.textContent = 'Username is available';
                        feedback.style.color = '#198754';
                    } else {
                        feedback.textContent = 'Username is already taken';
                        feedback.style.color = '#dc3545';
                    }
                })
                .catch(error => console.error('Error:', error));
            }, 500);
        });
    }
    
    // Real-time email format validation
    const emailInput = document.getElementById('email');
    if (emailInput) {
        emailInput.addEventListener('blur', function() {
            const email = this.value.trim();
            const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
            const feedback = document.getElementById('email-feedback') || 
                            createFeedbackElement(emailInput, 'email-feedback');
            
            if (!emailRegex.test(email)) {
                feedback.textContent = 'Please enter a valid email address';
                feedback.style.color = '#dc3545';
            } else {
                feedback.textContent = '';
            }
        });
    }
    
    // Password confirmation match
    const passwordInput = document.getElementById('password');
    const confirmPasswordInput = document.getElementById('confirm_password');
    
    if (passwordInput && confirmPasswordInput) {
        confirmPasswordInput.addEventListener('input', function() {
            const feedback = document.getElementById('confirm-password-feedback') || 
                            createFeedbackElement(confirmPasswordInput, 'confirm-password-feedback');
            
            if (this.value !== passwordInput.value) {
                feedback.textContent = 'Passwords do not match';
                feedback.style.color = '#dc3545';
            } else {
                feedback.textContent = 'Passwords match';
                feedback.style.color = '#198754';
            }
        });
    }
    
    function createFeedbackElement(inputElement, id) {
        const feedback = document.createElement('div');
        feedback.id = id;
        feedback.className = 'form-text';
        inputElement.parentNode.appendChild(feedback);
        return feedback;
    }
});