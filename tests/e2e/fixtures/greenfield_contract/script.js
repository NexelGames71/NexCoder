document.addEventListener('DOMContentLoaded', () => {
  const toggle = document.getElementById('theme-toggle');
  toggle.addEventListener('click', () => {
    document.body.classList.toggle('dark-theme');
  });
});
