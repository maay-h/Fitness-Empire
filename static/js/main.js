document.addEventListener('DOMContentLoaded', function() {
    updateDateDisplay();
    setupBalanceToggle();
    setupAutoBalance();
    setupSearchFilter();
    setupDeleteConfirm();
    setupThemeToggle();
    setupNameAutoCapitalize();
    setupDateValidation();
});

function updateDateDisplay() {
    const el = document.getElementById('current-date');
    if (el) {
        const options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
        el.textContent = new Date().toLocaleDateString('en-US', options);
    }
}

function setupBalanceToggle() {
    const toggles = document.querySelectorAll('input[name="has_balance"]');
    toggles.forEach(toggle => {
        toggle.addEventListener('change', function() {
            const form = this.closest('form');
            const balanceFields = form.querySelector('.balance-fields');
            if (this.value === 'yes') {
                balanceFields.classList.add('show');
                balanceFields.querySelectorAll('input').forEach(inp => inp.required = true);
            } else {
                balanceFields.classList.remove('show');
                balanceFields.querySelectorAll('input').forEach(inp => {
                    inp.required = false;
                    if (inp.name !== 'balance_amount') inp.value = '';
                });
                const priceInput = form.querySelector('#price');
                const paidInput = form.querySelector('#amount_paid');
                if (priceInput && paidInput) {
                    const price = parseFloat(priceInput.value) || 0;
                    paidInput.value = price.toFixed(2);
                }
            }
        });
    });
}

function setupAutoBalance() {
    const priceInput = document.getElementById('price');
    const paidInput = document.getElementById('amount_paid');
    if (!priceInput || !paidInput) return;

    function updateBalance() {
        const price = parseFloat(priceInput.value) || 0;
        const paid = parseFloat(paidInput.value) || 0;
        const diff = price - paid;

        const form = priceInput.closest('form');
        const balanceYes = form.querySelector('#balance_yes');
        const balanceNo = form.querySelector('#balance_no');
        const balanceInput = form.querySelector('#balance_amount');
        const balanceFields = form.querySelector('.balance-fields');

        if (diff > 0) {
            balanceYes.checked = true;
            balanceFields.classList.add('show');
            balanceInput.value = diff.toFixed(2);
            balanceInput.required = true;
        } else {
            balanceNo.checked = true;
            balanceFields.classList.remove('show');
            balanceInput.value = '0';
            balanceInput.required = false;
            paidInput.value = price.toFixed(2);
        }
    }

    priceInput.addEventListener('input', updateBalance);
    paidInput.addEventListener('input', updateBalance);
}

function setupSearchFilter() {
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.addEventListener('input', function() {
            const query = this.value.toLowerCase();
            const rows = document.querySelectorAll('tbody tr');
            rows.forEach(row => {
                const text = row.textContent.toLowerCase();
                row.style.display = text.includes(query) ? '' : 'none';
            });
        });
    }
}

function setupDeleteConfirm() {
    document.querySelectorAll('.delete-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            if (!confirm('Are you sure you want to delete this member? This action cannot be undone.')) {
                e.preventDefault();
            }
        });
    });
}

function setupThemeToggle() {
    const toggle = document.getElementById('themeToggle');
    if (!toggle) return;

    const currentTheme = localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', currentTheme);
    toggle.checked = currentTheme === 'light';
    updateThemeIcon(currentTheme);

    toggle.addEventListener('change', function() {
        const theme = this.checked ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
        updateThemeIcon(theme);
    });
}

function updateThemeIcon(theme) {
    const icon = document.querySelector('#themeIcon');
    if (icon) {
        icon.textContent = theme === 'light' ? 'light_mode' : 'dark_mode';
    }
}

function setupNameAutoCapitalize() {
    const nameInput = document.getElementById('name');
    if (!nameInput) return;
    nameInput.addEventListener('input', function() {
        this.value = this.value.replace(/\w\S*/g, function(txt) {
            return txt.charAt(0).toUpperCase() + txt.slice(1).toLowerCase();
        });
    });
}

function setupDateValidation() {
    document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', function(e) {
            const start = this.querySelector('#joining_date') || this.querySelector('#start_date');
            const end = this.querySelector('#expiry_date');
            if (start && end && start.value && end.value && end.value < start.value) {
                e.preventDefault();
                alert('Error: Expiry date cannot be before the start/joining date.');
            }
        });
    });
}
