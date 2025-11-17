/**
 * SendBaba Dashboard JavaScript
 * Professional Implementation
 */

const Dashboard = {
    chart: null,
    currentMonth: new Date(),

    /**
     * Initialize dashboard
     */
    init() {
        console.log('📊 SendBaba Dashboard v2.0');
        this.setupMobileMenu();
        this.setupEventListeners();
    },

    /**
     * Setup mobile menu toggle
     */
    setupMobileMenu() {
        const toggleBtn = document.querySelector('.mobile-menu-toggle');
        const sidebar = document.querySelector('.sidebar-container');
        
        if (toggleBtn && sidebar) {
            toggleBtn.addEventListener('click', () => {
                sidebar.classList.toggle('active');
            });

            // Close sidebar when clicking outside
            document.addEventListener('click', (e) => {
                if (window.innerWidth <= 1024) {
                    if (!sidebar.contains(e.target) && !toggleBtn.contains(e.target)) {
                        sidebar.classList.remove('active');
                    }
                }
            });
        }
    },

    /**
     * Setup event listeners
     */
    setupEventListeners() {
        // Calendar navigation
        const prevBtn = document.querySelector('.calendar-prev');
        const nextBtn = document.querySelector('.calendar-next');
        
        if (prevBtn) prevBtn.addEventListener('click', () => this.prevMonth());
        if (nextBtn) nextBtn.addEventListener('click', () => this.nextMonth());
    },

    /**
     * Initialize performance chart
     */
    initChart() {
        const canvas = document.getElementById('performanceChart');
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        
        this.chart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
                datasets: [{
                    label: 'Performance',
                    data: [78, 34, 87, 28, 39, 62],
                    backgroundColor: '#FF6B4A',
                    borderRadius: 8,
                    barThickness: 32
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        backgroundColor: '#1F2937',
                        padding: 12,
                        cornerRadius: 8,
                        displayColors: false,
                        callbacks: {
                            label: (context) => context.parsed.y + '%'
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 100,
                        ticks: {
                            callback: (value) => value + '%',
                            font: { size: 11 },
                            color: '#9CA3AF'
                        },
                        grid: {
                            color: '#F3F4F6',
                            drawBorder: false
                        }
                    },
                    x: {
                        ticks: {
                            font: { size: 11 },
                            color: '#9CA3AF'
                        },
                        grid: {
                            display: false,
                            drawBorder: false
                        }
                    }
                }
            }
        });
    },

    /**
     * Navigate to previous month
     */
    prevMonth() {
        this.currentMonth.setMonth(this.currentMonth.getMonth() - 1);
        this.updateCalendar();
    },

    /**
     * Navigate to next month
     */
    nextMonth() {
        this.currentMonth.setMonth(this.currentMonth.getMonth() + 1);
        this.updateCalendar();
    },

    /**
     * Update calendar display
     */
    updateCalendar() {
        const monthEl = document.querySelector('.calendar-month');
        if (monthEl) {
            const months = [
                'January', 'February', 'March', 'April', 'May', 'June',
                'July', 'August', 'September', 'October', 'November', 'December'
            ];
            monthEl.textContent = `${months[this.currentMonth.getMonth()]} ${this.currentMonth.getFullYear()}`;
        }
    },

    /**
     * Format number with commas
     */
    formatNumber(num) {
        return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    }
};

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    Dashboard.init();
    
    // Initialize chart if Chart.js is loaded
    if (typeof Chart !== 'undefined') {
        Dashboard.initChart();
    }
});

// Export for global access
window.Dashboard = Dashboard;
