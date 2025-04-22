/**
 * Chart Utilities for Dashboard Visualizations
 */

class ChartManager {
    constructor() {
        this.charts = {};
        this.initializeCharts();
    }

    /**
     * Initialize all chart objects
     */
    initializeCharts() {
        // Overview page charts
        this.initializeMessageActivityChart();
        this.initializeChannelChart();
        this.initializeUserChart();
        this.initializeHourlyChart();
        
        // Messages page charts
        this.initializeMessageTrendsChart();
        this.initializeMessageLengthChart();
        this.initializeWeekdayChart();
        this.initializeHourDistributionChart();
        
        // User page charts
        this.initializeUserTrendsChart();
        this.initializeUserActivityChart();
        
        // AI page charts
        this.initializeAIDailyChart();
        this.initializeAIModelsChart();
        this.initializeAIUsersChart();
    }

    /**
     * Create a new chart instance
     */
    createChart(canvasId, type, data, options = {}) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) {
            console.error(`Canvas element with ID ${canvasId} not found`);
            return null;
        }
        
        const ctx = canvas.getContext('2d');
        
        // Merge options with default chart options
        const chartOptions = {
            ...DashboardConfig.chartOptions,
            ...options
        };
        
        // Clear existing chart if it exists
        if (this.charts[canvasId]) {
            this.charts[canvasId].destroy();
        }
        
        // Create new chart
        this.charts[canvasId] = new Chart(ctx, {
            type: type,
            data: data,
            options: chartOptions
        });
        
        return this.charts[canvasId];
    }

    /**
     * Format dates for chart labels
     */
    formatDates(dates) {
        return dates.map(date => moment(date).format('MMM D'));
    }
    
    /**
     * Initialize Daily Message Activity Chart
     */
    initializeMessageActivityChart() {
        const data = {
            labels: [],
            datasets: [{
                label: 'Messages',
                data: [],
                backgroundColor: DashboardConfig.chartColors[0],
                borderColor: DashboardConfig.chartColors[0],
                borderWidth: 2,
                tension: 0.4,
                fill: false
            }]
        };
        
        const options = {
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Message Count'
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: 'Date'
                    }
                }
            }
        };
        
        this.createChart('messageActivityChart', 'line', data, options);
    }
    
    /**
     * Initialize Channel Distribution Chart
     */
    initializeChannelChart() {
        const data = {
            labels: [],
            datasets: [{
                label: 'Messages',
                data: [],
                backgroundColor: DashboardConfig.chartColors,
                borderWidth: 1
            }]
        };
        
        this.createChart('channelChart', 'doughnut', data);
    }
    
    /**
     * Initialize User Distribution Chart
     */
    initializeUserChart() {
        const data = {
            labels: [],
            datasets: [{
                label: 'Messages',
                data: [],
                backgroundColor: DashboardConfig.chartColors,
                borderWidth: 1
            }]
        };
        
        this.createChart('userChart', 'bar', data, {
            indexAxis: 'y'
        });
    }
    
    /**
     * Initialize Hourly Distribution Chart
     */
    initializeHourlyChart() {
        // Create labels for 24 hours
        const labels = Array.from({length: 24}, (_, i) => {
            const hour = i % 12 === 0 ? 12 : i % 12;
            return `${hour}${i < 12 ? ' AM' : ' PM'}`;
        });
        
        const data = {
            labels: labels,
            datasets: [{
                label: 'Messages',
                data: Array(24).fill(0),
                backgroundColor: DashboardConfig.chartColors[0],
                borderColor: DashboardConfig.chartColors[0],
                borderWidth: 1
            }]
        };
        
        const options = {
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Message Count'
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: 'Hour of Day'
                    }
                }
            }
        };
        
        this.createChart('hourlyChart', 'bar', data, options);
    }
    
    /**
     * Initialize Message Trends Chart
     */
    initializeMessageTrendsChart() {
        const data = {
            labels: [],
            datasets: [{
                label: 'Messages',
                data: [],
                backgroundColor: DashboardConfig.chartColors[0],
                borderColor: DashboardConfig.chartColors[0],
                borderWidth: 2,
                tension: 0.4,
                fill: true
            }]
        };
        
        const options = {
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Message Count'
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: 'Date'
                    }
                }
            }
        };
        
        this.createChart('messageTrendsChart', 'line', data, options);
    }
    
    /**
     * Initialize Message Length Distribution Chart
     */
    initializeMessageLengthChart() {
        const data = {
            labels: ['Very Short', 'Short', 'Medium', 'Long'],
            datasets: [{
                label: 'Messages',
                data: [],
                backgroundColor: [
                    DashboardConfig.chartColors[0],
                    DashboardConfig.chartColors[1],
                    DashboardConfig.chartColors[2],
                    DashboardConfig.chartColors[3]
                ],
                borderWidth: 1
            }]
        };
        
        this.createChart('messageLengthChart', 'pie', data);
    }
    
    /**
     * Initialize Weekday Distribution Chart
     */
    initializeWeekdayChart() {
        const data = {
            labels: ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'],
            datasets: [{
                label: 'Messages',
                data: Array(7).fill(0),
                backgroundColor: DashboardConfig.chartColors[0],
                borderColor: DashboardConfig.chartColors[0],
                borderWidth: 1
            }]
        };
        
        this.createChart('weekdayChart', 'bar', data);
    }
    
    /**
     * Initialize Hour Distribution Chart
     */
    initializeHourDistributionChart() {
        const labels = Array.from({length: 24}, (_, i) => `${i}:00`);
        
        const data = {
            labels: labels,
            datasets: [{
                label: 'Messages',
                data: Array(24).fill(0),
                backgroundColor: DashboardConfig.chartColors[0],
                borderColor: DashboardConfig.chartColors[0],
                borderWidth: 1,
                fill: true
            }]
        };
        
        this.createChart('hourDistributionChart', 'line', data, {
            scales: {
                y: {
                    beginAtZero: true
                }
            }
        });
    }
    
    /**
     * Initialize User Trends Chart
     */
    initializeUserTrendsChart() {
        const data = {
            labels: [],
            datasets: [{
                label: 'User Growth',
                data: [],
                backgroundColor: DashboardConfig.chartColors[1],
                borderColor: DashboardConfig.chartColors[1],
                borderWidth: 2,
                tension: 0.4
            }]
        };
        
        this.createChart('userTrendsChart', 'line', data);
    }
    
    /**
     * Initialize User Activity Chart
     */
    initializeUserActivityChart() {
        const data = {
            labels: [],
            datasets: []
        };
        
        const options = {
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Message Count'
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: 'Date'
                    }
                }
            }
        };
        
        this.createChart('userActivityChart', 'line', data, options);
    }
    
    /**
     * Initialize AI Daily Chart
     */
    initializeAIDailyChart() {
        const data = {
            labels: [],
            datasets: [{
                label: 'AI Interactions',
                data: [],
                backgroundColor: DashboardConfig.chartColors[5],
                borderColor: DashboardConfig.chartColors[5],
                borderWidth: 2,
                tension: 0.4
            }]
        };
        
        const options = {
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Interaction Count'
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: 'Date'
                    }
                }
            }
        };
        
        this.createChart('aiDailyChart', 'line', data, options);
    }
    
    /**
     * Initialize AI Models Chart
     */
    initializeAIModelsChart() {
        const data = {
            labels: [],
            datasets: [{
                label: 'Interactions',
                data: [],
                backgroundColor: DashboardConfig.chartColors,
                borderWidth: 1
            }]
        };
        
        this.createChart('aiModelsChart', 'doughnut', data);
    }
    
    /**
     * Initialize AI Users Chart
     */
    initializeAIUsersChart() {
        const data = {
            labels: [],
            datasets: [{
                label: 'AI Interactions',
                data: [],
                backgroundColor: DashboardConfig.chartColors,
                borderWidth: 1
            }]
        };
        
        this.createChart('aiUsersChart', 'bar', data, {
            indexAxis: 'y'
        });
    }

    /**
     * Update Message Activity Chart with data
     */
    updateMessageActivityChart(data) {
        if (!data || !data.daily_counts || !this.charts.messageActivityChart) return;
        
        const chart = this.charts.messageActivityChart;
        const dailyData = data.daily_counts;
        
        chart.data.labels = this.formatDates(dailyData.map(item => item.date));
        chart.data.datasets[0].data = dailyData.map(item => item.count);
        
        chart.update();
    }
    
    /**
     * Update Channel Chart with data
     */
    updateChannelChart(data) {
        if (!data || !data.channel_stats || !this.charts.channelChart) return;
        
        const chart = this.charts.channelChart;
        const channelData = data.channel_stats.slice(0, 5); // Take top 5
        
        chart.data.labels = channelData.map(item => item.channel_name);
        chart.data.datasets[0].data = channelData.map(item => item.message_count);
        
        chart.update();
    }
    
    /**
     * Update User Chart with data
     */
    updateUserChart(data) {
        if (!data || !data.top_users || !this.charts.userChart) return;
        
        const chart = this.charts.userChart;
        const userData = data.top_users.slice(0, 5); // Take top 5
        
        chart.data.labels = userData.map(item => item.username);
        chart.data.datasets[0].data = userData.map(item => item.message_count);
        
        chart.update();
    }
    
    /**
     * Update Hourly Chart with data
     */
    updateHourlyChart(data) {
        if (!data || !data.hourly_distribution || !this.charts.hourlyChart) return;
        
        const chart = this.charts.hourlyChart;
        const hourlyData = data.hourly_distribution;
        
        // Reset data
        const hourCounts = Array(24).fill(0);
        
        // Populate hours that have data
        hourlyData.forEach(item => {
            hourCounts[parseInt(item.hour)] = item.count;
        });
        
        chart.data.datasets[0].data = hourCounts;
        
        chart.update();
    }
    
    /**
     * Update Message Trends Chart with data
     */
    updateMessageTrendsChart(data) {
        if (!data || !data.daily_counts || !this.charts.messageTrendsChart) return;
        
        const chart = this.charts.messageTrendsChart;
        const dailyData = data.daily_counts;
        
        chart.data.labels = this.formatDates(dailyData.map(item => item.date));
        chart.data.datasets[0].data = dailyData.map(item => item.count);
        
        chart.update();
    }
    
    /**
     * Update Message Length Chart with data
     */
    updateMessageLengthChart(data) {
        if (!data || !data.length_distribution || !this.charts.messageLengthChart) return;
        
        const chart = this.charts.messageLengthChart;
        const lengthData = data.length_distribution;
        
        // Map the categories to the expected order
        const categories = ['Very Short', 'Short', 'Medium', 'Long'];
        const counts = categories.map(category => {
            const found = lengthData.find(item => item.category === category);
            return found ? found.count : 0;
        });
        
        chart.data.datasets[0].data = counts;
        
        chart.update();
    }
    
    /**
     * Update Weekday Chart with data
     */
    updateWeekdayChart(data) {
        if (!data || !data.weekday_distribution || !this.charts.weekdayChart) return;
        
        const chart = this.charts.weekdayChart;
        const weekdayData = data.weekday_distribution;
        
        // Reset data
        const weekdayCounts = Array(7).fill(0);
        
        // Populate weekdays that have data
        weekdayData.forEach(item => {
            weekdayCounts[parseInt(item.weekday)] = item.count;
        });
        
        chart.data.datasets[0].data = weekdayCounts;
        
        chart.update();
    }
    
    /**
     * Update Hour Distribution Chart with data
     */
    updateHourDistributionChart(data) {
        if (!data || !data.hourly_distribution || !this.charts.hourDistributionChart) return;
        
        const chart = this.charts.hourDistributionChart;
        const hourlyData = data.hourly_distribution;
        
        // Reset data
        const hourCounts = Array(24).fill(0);
        
        // Populate hours that have data
        hourlyData.forEach(item => {
            hourCounts[parseInt(item.hour)] = item.count;
        });
        
        chart.data.datasets[0].data = hourCounts;
        
        chart.update();
    }
    
    /**
     * Update User Trends Chart with data
     */
    updateUserTrendsChart(data) {
        if (!data || !data.user_trends || !this.charts.userTrendsChart) return;
        
        const chart = this.charts.userTrendsChart;
        
        // Take the first user's trend data
        if (data.user_trends.length > 0) {
            const trendData = data.user_trends[0].trend;
            
            chart.data.labels = this.formatDates(trendData.map(item => item.date));
            chart.data.datasets[0].data = trendData.map(item => item.count);
            
            chart.update();
        }
    }
    
    /**
     * Update User Activity Chart with multiple users' data
     */
    updateUserActivityChart(data) {
        if (!data || !data.user_trends || !this.charts.userActivityChart) return;
        
        const chart = this.charts.userActivityChart;
        const userTrends = data.user_trends.slice(0, 5); // Take top 5 users
        
        if (userTrends.length === 0) return;
        
        // Get all dates from the first user (assuming all users have the same date range)
        const dates = userTrends[0].trend.map(item => item.date);
        
        // Create datasets for each user
        const datasets = userTrends.map((user, index) => {
            const colorIndex = index % DashboardConfig.chartColors.length;
            
            return {
                label: user.username,
                data: user.trend.map(item => item.count),
                backgroundColor: DashboardConfig.chartColors[colorIndex],
                borderColor: DashboardConfig.chartColors[colorIndex],
                borderWidth: 2,
                tension: 0.4,
                fill: false
            };
        });
        
        chart.data.labels = this.formatDates(dates);
        chart.data.datasets = datasets;
        
        chart.update();
    }
    
    /**
     * Update AI Daily Chart with data
     */
    updateAIDailyChart(data) {
        if (!data || !data.ai_daily || !this.charts.aiDailyChart) return;
        
        const chart = this.charts.aiDailyChart;
        const dailyData = data.ai_daily;
        
        chart.data.labels = this.formatDates(dailyData.map(item => item.date));
        chart.data.datasets[0].data = dailyData.map(item => item.count);
        
        chart.update();
    }
    
    /**
     * Update AI Models Chart with data
     */
    updateAIModelsChart(data) {
        if (!data || !data.ai_models || !this.charts.aiModelsChart) return;
        
        const chart = this.charts.aiModelsChart;
        const modelsData = data.ai_models;
        
        chart.data.labels = modelsData.map(item => item.model);
        chart.data.datasets[0].data = modelsData.map(item => item.count);
        
        chart.update();
    }
    
    /**
     * Update AI Users Chart with data
     */
    updateAIUsersChart(data) {
        if (!data || !data.ai_users || !this.charts.aiUsersChart) return;
        
        const chart = this.charts.aiUsersChart;
        const usersData = data.ai_users;
        
        chart.data.labels = usersData.map(item => item.username);
        chart.data.datasets[0].data = usersData.map(item => item.count);
        
        chart.update();
    }
}

// Create global chart manager instance
const chartManager = new ChartManager();