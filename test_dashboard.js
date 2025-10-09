const fs = require('fs');
const path = require('path');

// Read the dashboard HTML
const dashboardPath = path.join(__dirname, 'web_interface', 'dashboard.html');
const html = fs.readFileSync(dashboardPath, 'utf-8');

// Extract the embedded data
const dataMatch = html.match(/const EMBEDDED_DATA_ALL_MONTHS = ({[\s\S]*?});/);
const manifestMatch = html.match(/const EMBEDDED_MANIFEST = ({[\s\S]*?});/);

if (!dataMatch) {
    console.error('❌ EMBEDDED_DATA_ALL_MONTHS not found!');
    process.exit(1);
}

if (!manifestMatch) {
    console.error('❌ EMBEDDED_MANIFEST not found!');
    process.exit(1);
}

try {
    // Parse the data
    const EMBEDDED_DATA_ALL_MONTHS = JSON.parse(dataMatch[1]);
    const EMBEDDED_MANIFEST = JSON.parse(manifestMatch[1]);

    console.log('✅ Dashboard data structure is valid\n');

    // Check months
    const months = Object.keys(EMBEDDED_DATA_ALL_MONTHS);
    console.log(`📅 Available months: ${months.join(', ')}`);
    console.log(`📅 Total months: ${months.length}\n`);

    // Check reports for each month
    months.forEach(month => {
        const monthData = EMBEDDED_DATA_ALL_MONTHS[month];
        const reportCount = monthData.reports ? monthData.reports.length : 0;
        console.log(`\n📊 Month: ${month}`);
        console.log(`   Reports: ${reportCount}`);
        console.log(`   Metadata total_files: ${monthData.analysis_metadata.total_files}`);

        if (monthData.reports) {
            monthData.reports.forEach((report, idx) => {
                console.log(`   - Report ${idx + 1}: ${report.file_info.name} (${report.report_type})`);
                console.log(`     Status: ${report.result_status}, Score: ${report.score}`);
            });
        }
    });

    console.log('\n✅ All data checks passed!');

} catch (error) {
    console.error('❌ Error parsing dashboard data:', error.message);
    process.exit(1);
}
