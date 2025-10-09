const fs = require('fs');
const path = require('path');

// Read the dashboard HTML
const dashboardPath = path.join(__dirname, 'web_interface', 'dashboard.html');
const html = fs.readFileSync(dashboardPath, 'utf-8');

// Extract the embedded data
const dataMatch = html.match(/const EMBEDDED_DATA_ALL_MONTHS = ({[\s\S]*?});/);

if (!dataMatch) {
    console.error('❌ EMBEDDED_DATA_ALL_MONTHS not found!');
    process.exit(1);
}

try {
    const EMBEDDED_DATA_ALL_MONTHS = JSON.parse(dataMatch[1]);
    const months = Object.keys(EMBEDDED_DATA_ALL_MONTHS);

    console.log('='.repeat(60));
    console.log('📅 MONTH DROPDOWN VERIFICATION');
    console.log('='.repeat(60));
    console.log();

    console.log(`✅ Total months available in dropdown: ${months.length}`);
    console.log();

    console.log('Month entries (as they would appear in dropdown):');
    months.forEach((month, index) => {
        const monthData = EMBEDDED_DATA_ALL_MONTHS[month];
        const reportCount = monthData.reports ? monthData.reports.length : 0;
        const totalFiles = monthData.analysis_metadata.total_files;

        // Format month for display (like in dashboard)
        const [year, monthNum] = month.split('-');
        const date = new Date(parseInt(year), parseInt(monthNum) - 1, 1);
        const monthLabel = date.toLocaleDateString('de-DE', { month: 'long', year: 'numeric' });

        console.log(`  ${index + 1}. ${monthLabel} (${totalFiles} Bericht(e))`);
        console.log(`     Month key: ${month}`);
        console.log(`     Reports in data: ${reportCount}`);
        console.log();
    });

    // Verify May 2025 specifically
    if (months.includes('2025-05')) {
        console.log('✅ SUCCESS: 2025-05 (Mai 2025) is present in the dropdown!');
        const mayData = EMBEDDED_DATA_ALL_MONTHS['2025-05'];
        console.log(`   - Report count: ${mayData.reports.length}`);
        console.log(`   - Report file: ${mayData.reports[0].file_info.name}`);

        // Check html_filename
        if (mayData.analysis_metadata.html_filename) {
            console.log(`   - HTML filename: ${mayData.analysis_metadata.html_filename}`);
            console.log('   - Detail report link will work ✓');
        } else {
            console.log('   ⚠️  Warning: html_filename missing, link may not work');
        }
    } else {
        console.error('❌ FAILURE: 2025-05 (Mai 2025) is NOT in the dropdown!');
        process.exit(1);
    }

    console.log();
    console.log('='.repeat(60));

} catch (error) {
    console.error('❌ Error parsing dashboard data:', error.message);
    process.exit(1);
}
