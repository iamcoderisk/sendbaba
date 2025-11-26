document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 SendBaba Dashboard initializing...');
    initMobileMenu();
    initUserMenu();
    initUpgradeCardPulse();
    console.log('✅ SendBaba Dashboard initialized');
});

/* ==================== MOBILE MENU ==================== */
function initMobileMenu() {
    var menuBtn = document.getElementById('mobile-menu-btn');
    var sidebar = document.getElementById('sidebar') || document.querySelector('.sidebar');
    var overlay = document.getElementById('mobile-overlay');
    
    console.log('Mobile menu init:', { menuBtn: !!menuBtn, sidebar: !!sidebar, overlay: !!overlay });
    
    if (!menuBtn) {
        console.warn('Mobile menu button not found - creating it dynamically');
        createMobileElements();
        menuBtn = document.getElementById('mobile-menu-btn');
        overlay = document.getElementById('mobile-overlay');
    }
    
    if (!menuBtn || !sidebar) {
        console.error('Required elements not found');
        return;
    }
    
    menuBtn.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        console.log('Mobile menu clicked');
        
        sidebar.classList.toggle('mobile-open');
        if (overlay) overlay.classList.toggle('show');
        
        var icon = menuBtn.querySelector('i');
        if (icon) {
            if (sidebar.classList.contains('mobile-open')) {
                icon.className = 'fas fa-times';
            } else {
                icon.className = 'fas fa-bars';
            }
        }
    });
    
    if (overlay) {
        overlay.addEventListener('click', function() {
            sidebar.classList.remove('mobile-open');
            overlay.classList.remove('show');
            var icon = menuBtn.querySelector('i');
            if (icon) icon.className = 'fas fa-bars';
        });
    }
    
    // Close sidebar when clicking a link on mobile
    var links = sidebar.querySelectorAll('.sidebar-link');
    links.forEach(function(link) {
        link.addEventListener('click', function() {
            if (window.innerWidth <= 768) {
                sidebar.classList.remove('mobile-open');
                if (overlay) overlay.classList.remove('show');
                var icon = menuBtn.querySelector('i');
                if (icon) icon.className = 'fas fa-bars';
            }
        });
    });
    
    console.log('✅ Mobile menu initialized');
}

function createMobileElements() {
    // Create overlay
    if (!document.getElementById('mobile-overlay')) {
        var overlay = document.createElement('div');
        overlay.id = 'mobile-overlay';
        overlay.className = 'mobile-overlay';
        document.body.appendChild(overlay);
    }
    
    // Create mobile menu button
    if (!document.getElementById('mobile-menu-btn')) {
        var btn = document.createElement('button');
        btn.id = 'mobile-menu-btn';
        btn.className = 'mobile-menu-btn';
        btn.setAttribute('aria-label', 'Toggle menu');
        btn.innerHTML = '<i class="fas fa-bars"></i>';
        document.body.appendChild(btn);
    }
}

/* ==================== USER MENU ==================== */
function initUserMenu() {
    var profile = document.querySelector('.user-profile');
    var menu = document.getElementById('userMenu') || document.querySelector('.user-menu');
    
    if (!profile || !menu) {
        console.warn('User menu elements not found');
        return;
    }
    
    profile.addEventListener('click', function(e) {
        e.stopPropagation();
        menu.classList.toggle('show');
    });
    
    document.addEventListener('click', function(e) {
        if (!menu.contains(e.target) && !profile.contains(e.target)) {
            menu.classList.remove('show');
        }
    });
    
    console.log('✅ User menu initialized');
}

function toggleUserMenu() {
    var menu = document.getElementById('userMenu') || document.querySelector('.user-menu');
    if (menu) menu.classList.toggle('show');
}

/* ==================== UPGRADE CARD PULSE ==================== */
function initUpgradeCardPulse() {
    var card = document.getElementById('upgradeCard');
    if (!card) return;
    
    setInterval(function() {
        card.style.transform = 'translateY(-2px) scale(1.02)';
        card.style.boxShadow = '0 8px 20px rgba(247, 96, 31, 0.4)';
        setTimeout(function() {
            card.style.transform = '';
            card.style.boxShadow = '';
        }, 1500);
    }, 60000);
    
    // Initial pulse after 3 seconds
    setTimeout(function() {
        card.style.transform = 'translateY(-2px) scale(1.02)';
        card.style.boxShadow = '0 8px 20px rgba(247, 96, 31, 0.4)';
        setTimeout(function() {
            card.style.transform = '';
            card.style.boxShadow = '';
        }, 1500);
    }, 3000);
    
    console.log('✅ Upgrade card pulse initialized');
}
