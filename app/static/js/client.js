document.querySelectorAll('.toggle').forEach(button => {
  button.addEventListener('click', () => {
    const input = document.getElementById(button.getAttribute('aria-controls'));
    const visible = input.type === 'password';
    input.type = visible ? 'text' : 'password';
    button.textContent = visible ? 'Hide' : 'Show';
    button.setAttribute('aria-label', visible ? 'Hide password' : 'Show password');
    button.setAttribute('aria-pressed', String(visible));
  });
});

const loginForm = document.querySelector('[data-js-login]');

if (loginForm) {
  loginForm.addEventListener('submit', async event => {
    event.preventDefault();

    const message = loginForm.querySelector('[role="status"]');
    const submitButton = loginForm.querySelector('[type="submit"]');
    const formData = new FormData(loginForm);

    submitButton.disabled = true;
    message.textContent = 'Checking your login...';

    try {
      const response = await fetch(loginForm.action, {
        method: 'POST',
        body: formData,
        headers: {
          'X-Requested-With': 'XMLHttpRequest'
        }
      });
      const result = await response.json();

      message.textContent = result.message;

      if (response.ok) {
        setTimeout(() => {
          window.location.href = result.redirect_url;
        }, 900);
      }
    } catch (error) {
      message.textContent = 'Something went wrong. Please try again.';
    } finally {
      submitButton.disabled = false;
    }
  });
}
