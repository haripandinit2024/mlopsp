/**
 * Student Dropout Risk Dashboard - Frontend Logic
 */

const API_BASE = '';

// --------------------------------------------------------
// Student View
// --------------------------------------------------------
async function lookupStudent() {
    const id = parseInt(document.getElementById('studentIdInput').value);
    if (!id || id < 1 || id > 10000) {
        alert('Please enter a valid Student ID (1-10000)');
        return;
    }

    try {
        const res = await fetch(`${API_BASE}/api/student/${id}`);
        const data = await res.json();

        if (data.error) {
            alert(data.error);
            return;
        }

        showStudentResult(data);
    } catch (err) {
        console.error('Error fetching student:', err);
        alert('Failed to fetch student data. Make sure the server is running.');
    }
}

async function predictCustom() {
    const data = {
        GPA: parseFloat(document.getElementById('inputGPA').value),
        Attendance_Rate: parseFloat(document.getElementById('inputAttendance').value),
        Stress_Index: parseFloat(document.getElementById('inputStress').value),
        Study_Hours_per_Day: parseFloat(document.getElementById('inputStudyHours').value),
        Semester_GPA: parseFloat(document.getElementById('inputSemesterGPA').value),
        Assignment_Delay_Days: parseInt(document.getElementById('inputDelay').value),
        // Defaults for fields the API needs
        Age: 20,
        Family_Income: 30000,
        Travel_Time_Minutes: 30,
        CGPA: 3.0,
        Gender: 'Male',
        Internet_Access: 'Yes',
        Part_Time_Job: 'No',
        Scholarship: 'No',
        Department: 'CS',
        Semester: 'Year 1',
        Parental_Education: 'Bachelor',
    };

    try {
        const res = await fetch(`${API_BASE}/api/predict`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        const result = await res.json();

        if (result.error) {
            alert(result.error);
            return;
        }

        showStudentResult({
            risk_probability: result.risk_probability,
            risk_tier: result.risk_tier,
            recommendations: result.recommendations,
            student_id: null,
        });
    } catch (err) {
        console.error('Error predicting:', err);
        alert('Failed to get prediction. Make sure the server is running.');
    }
}

function showStudentResult(data) {
    const resultCard = document.getElementById('studentResult');
    const gauge = document.querySelector('.risk-gauge');
    const valueEl = document.getElementById('studentRiskValue');
    const tierEl = document.getElementById('studentRiskTier');
    const barEl = document.getElementById('studentRiskBar');
    const detailsEl = document.getElementById('studentDetails');
    const recList = document.getElementById('studentRecList');

    const prob = data.risk_probability;
    const tier = data.risk_tier;

    // Set gauge
    valueEl.textContent = (prob * 100).toFixed(1) + '%';
    tierEl.textContent = tier;
    gauge.dataset.tier = tier;

    // Set bar
    barEl.style.width = (prob * 100) + '%';
    barEl.className = 'risk-bar ' + tier.toLowerCase();

    // Set details
    if (data.student_id) {
        detailsEl.innerHTML = `
            <div><strong>Student ID:</strong> ${data.student_id}</div>
            <div><strong>Department:</strong> ${data.department || '-'}</div>
            <div><strong>Year:</strong> ${data.semester || '-'}</div>
            <div><strong>GPA:</strong> ${data.gpa?.toFixed(2) || '-'}</div>
            <div><strong>Attendance:</strong> ${data.attendance_rate?.toFixed(1) || '-'}%</div>
            <div><strong>Stress:</strong> ${data.stress_index?.toFixed(1) || '-'}</div>
        `;
    } else {
        detailsEl.innerHTML = `
            <div><strong>GPA:</strong> ${document.getElementById('inputGPA').value}</div>
            <div><strong>Attendance:</strong> ${document.getElementById('inputAttendance').value}%</div>
            <div><strong>Stress:</strong> ${document.getElementById('inputStress').value}</div>
            <div><strong>Study Hours:</strong> ${document.getElementById('inputStudyHours').value}/day</div>
        `;
    }

    // Set recommendations
    recList.innerHTML = '';
    (data.recommendations || []).forEach(rec => {
        const li = document.createElement('li');
        li.textContent = rec;
        recList.appendChild(li);
    });

    resultCard.classList.remove('hidden');
    resultCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function hideResult(id) {
    document.getElementById(id).classList.add('hidden');
}

// --------------------------------------------------------
// Faculty View
// --------------------------------------------------------
async function loadFacultyStudents() {
    const dept = document.getElementById('facultyDept').value;
    const year = document.getElementById('facultyYear').value;

    try {
        const res = await fetch(`${API_BASE}/api/faculty/${dept}?semester=${encodeURIComponent(year)}`);
        const students = await res.json();

        const tbody = document.getElementById('facultyTableBody');
        const highCount = students.filter(s => s.risk_tier === 'High').length;
        const medCount = students.filter(s => s.risk_tier === 'Medium').length;

        // Update stats
        document.getElementById('facultyHigh').textContent = highCount;
        document.getElementById('facultyMedium').textContent = medCount;
        document.getElementById('facultyLow').textContent = Math.max(0, students.length - highCount - medCount);
        document.getElementById('facultyTotal').textContent = students.length;

        // Render table
        if (students.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="loading">No at-risk students found</td></tr>';
            return;
        }

        tbody.innerHTML = students.map(s => `
            <tr>
                <td><strong>${s.student_id}</strong></td>
                <td>${s.semester}</td>
                <td>${s.attendance.toFixed(1)}%</td>
                <td>${s.gpa.toFixed(2)}</td>
                <td>${s.stress.toFixed(1)}</td>
                <td>${(s.risk_probability * 100).toFixed(1)}%</td>
                <td><span class="tier-badge ${s.risk_tier.toLowerCase()}">${s.risk_tier}</span></td>
            </tr>
        `).join('');
    } catch (err) {
        console.error('Error loading faculty data:', err);
    }
}

// --------------------------------------------------------
// Admin View
// --------------------------------------------------------
async function loadAdminOverview() {
    try {
        const res = await fetch(`${API_BASE}/api/overview`);
        const data = await res.json();

        if (data.error) {
            console.error(data.error);
            return;
        }

        // Update stats
        document.getElementById('adminTotal').textContent = data.total_students.toLocaleString();
        document.getElementById('adminDropoutRate').textContent = (data.dropout_rate * 100).toFixed(1) + '%';
        document.getElementById('adminHighRisk').textContent = data.risk_distribution.High.toLocaleString();
        document.getElementById('adminMediumRisk').textContent = data.risk_distribution.Medium.toLocaleString();

        // Render department chart
        renderBarChart('deptChart', data.risk_by_department, 'primary');

        // Render year chart
        renderBarChart('yearChart', data.risk_by_year, 'primary');
    } catch (err) {
        console.error('Error loading overview:', err);
    }
}

function renderBarChart(containerId, data, colorClass) {
    const container = document.getElementById(containerId);
    const maxVal = Math.max(...Object.values(data), 0.01);

    container.innerHTML = '<div class="bar-chart">' +
        Object.entries(data)
            .sort((a, b) => b[1] - a[1])
            .map(([key, val]) => {
                const pct = (val / maxVal) * 100;
                const displayPct = (val * 100).toFixed(1);
                return `
                    <div class="bar-row">
                        <div class="bar-label">${key}</div>
                        <div class="bar-track">
                            <div class="bar-fill ${colorClass}" style="width: ${pct}%">${displayPct}%</div>
                        </div>
                    </div>
                `;
            }).join('') +
        '</div>';
}

// --------------------------------------------------------
// Init
// --------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
    // Check API health
    fetch(`${API_BASE}/api/health`)
        .then(res => res.json())
        .then(data => {
            document.getElementById('modelStatus').innerHTML =
                '<span class="status-dot"></span><span>Model Active</span>';
        })
        .catch(() => {
            document.getElementById('modelStatus').innerHTML =
                '<span class="status-dot" style="background: var(--danger);"></span><span>Offline</span>';
        });
});
