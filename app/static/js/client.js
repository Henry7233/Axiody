// add for the register/login page
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
document.querySelector('form').addEventListener('submit', event => {
  event.preventDefault();
  document.querySelector('[role="status"]').textContent = 'Preview only. The form is valid, but authentication is not connected yet.';
});