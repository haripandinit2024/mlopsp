/**
 * Student Dropout Risk Dashboard - Frontend Logic
 */

const API_BASE = '';

// --------------------------------------------------------
// Manual Risk Prediction (predictCustom)
// --------------------------------------------------------
async function predictCustom(event) {
    if (event) event.preventDefault();

    const gpa = parseFloat(document.getElementById('manualGpa').value);
    const attendance = parseFloat(document.getElementById('manualAttendance').value);
    const stress = parseFloat(document.getElementById('manualStress').value);
    const study = parseFloat(document.getElementById('manualStudy').value);
    const semGpa = parseFloat(document.getElementById('manualSemGpa').value) || null;
    const delay = parseFloat(document.getElementById('manualDelay').value) || null;

    if (isNaN(gpa) || isNaN(attendance) || isNaN(stress) || isNaN(study)) {
        alert('Please fill in all required fields (GPA, Attendance, Stress Index, Study Hours)');
        return false;
    }

    const payload = {
        GPA: gpa,
        Attendance_Rate: attendance,
        Stress_Index: stress,
        Study_Hours_per_Day: study,
    };

    if (semGpa !== null) payload.Semester_GPA = semGpa;
    if (delay !== null) payload.Assignment_Delay_Days = delay;

    try {
        const res = await safeFetch(`${API_BASE}/api/predict`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await res.json();

        if (data.error) {
            if (res.status === 401) {
                alert('Session expired. Please log in again.');
                window.location.href = '/login';
            } else {
                alert(data.error);
            }
            return false;
        }

        showStudentResult(data);
        return false;
    } catch (err) {
        console.error('Error predicting:', err);
        alert('Failed to predict risk. Make sure the server is running.');
        return false;
    }
}

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
        // Use safe fetch to handle 401 re-auth
        const res = await safeFetch(`${API_BASE}/api/student/${id}`);
        const data = await res.json();
        
        // Handle re-auth failure
        if (res.status === 401 && data.error) {
            alert('Session expired. Please log in again.');
            window.location.href = '/login';
            return;
        }

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
    const rows = [];
    if (data.student_id) rows.push(['Student ID', data.student_id]);
    if (data.department) rows.push(['Department', data.department]);
    if (data.semester) rows.push(['Year', data.semester]);
    if (data.gpa != null) rows.push(['GPA', data.gpa.toFixed(2)]);
    if (data.attendance_rate != null) rows.push(['Attendance', data.attendance_rate.toFixed(1) + '%']);
    if (data.stress_index != null) rows.push(['Stress', data.stress_index.toFixed(1)]);
    detailsEl.innerHTML = rows.map(([k, v]) => `<div><strong>${k}:</strong> ${v}</div>`).join('');

    renderStudentProfile(data);

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
// Student Dashboard - auto-load the logged-in student's own
// risk assessment (gauge + profile bars) on view open.
// --------------------------------------------------------
async function loadStudentDashboard() {
    const card = document.getElementById('studentOverviewCard');
    if (!card) return;
    const gauge = card.querySelector('.risk-gauge');
    const valueEl = document.getElementById('studentOverviewRisk');
    const tierEl = document.getElementById('studentOverviewTier');
    const chartEl = document.getElementById('studentOverviewChart');
    const detailsEl = document.getElementById('studentOverviewDetails');
    const recsEl = document.getElementById('studentOverviewRecs');

    try {
        const res = await safeFetch(`${API_BASE}/api/students/me`);
        if (res.status === 401) {
            gauge.dataset.tier = 'Medium';
            valueEl.textContent = '--';
            tierEl.textContent = 'Sign in required';
            return;
        }
        const data = await res.json();
        if (data.error || !data.student) {
            detailsEl.innerHTML = `<p class="loading" style="color:var(--text-muted);">${data.error || 'No student record linked.'}</p>`;
            if (res.status === 403) renderLinkStudentForm(detailsEl);
            return;
        }

        const s = data.student;
        valueEl.textContent = (s.risk_probability * 100).toFixed(1) + '%';
        tierEl.textContent = s.risk_tier;
        gauge.dataset.tier = s.risk_tier;

        const rows = [];
        if (s.student_id) rows.push(['Student ID', s.student_id]);
        if (s.department) rows.push(['Department', s.department]);
        if (s.semester) rows.push(['Year', s.semester]);
        if (s.gpa != null) rows.push(['GPA', s.gpa.toFixed(2)]);
        if (s.attendance_rate != null) rows.push(['Attendance', s.attendance_rate.toFixed(1) + '%']);
        if (s.stress_index != null) rows.push(['Stress', s.stress_index.toFixed(1)]);
        detailsEl.innerHTML = rows.map(([k, v]) => `<div><strong>${k}:</strong> ${v}</div>`).join('');

        renderStudentProfileInto(chartEl, s);
        recsEl.innerHTML = '';
        (s.recommendations || []).forEach(rec => {
            const li = document.createElement('li');
            li.textContent = rec;
            recsEl.appendChild(li);
        });
    } catch (err) {
        console.error('Error loading student dashboard:', err);
        gauge.dataset.tier = 'Medium';
        valueEl.textContent = '--';
        tierEl.textContent = 'Unavailable';
    }
}

// Renders the "link my student ID" form inside the overview card when the
// account has not been linked to a roster record yet.
function renderLinkStudentForm(container) {
    container.innerHTML = `
        <div class="link-student-box" style="margin-top:0.75rem;padding:1rem;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);">
            <p style="margin:0 0 0.75rem;font-size:0.875rem;color:var(--text-secondary);">Enter your Student ID to link this account to your risk profile.</p>
            <div class="input-group">
                <input type="number" id="linkStudentIdInput" min="1" max="10000" placeholder="Student ID (1-10000)">
                <button class="btn btn-primary" onclick="linkStudentRecord()">Link</button>
            </div>
            <p id="linkStudentMsg" class="loading" style="margin:0.5rem 0 0;font-size:0.8rem;"></p>
        </div>`;
}

async function linkStudentRecord() {
    const input = document.getElementById('linkStudentIdInput');
    const msg = document.getElementById('linkStudentMsg');
    const studentId = parseInt(input ? input.value : '', 10);
    if (!studentId || studentId < 1 || studentId > 10000) {
        if (msg) msg.textContent = 'Enter a valid Student ID (1-10000).';
        return;
    }
    if (msg) { msg.textContent = 'Linking...'; }

    try {
        const res = await safeFetch(`${API_BASE}/api/auth/link-student`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ student_id: studentId }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            if (res.status === 401) {
                alert('Session expired. Please log in again.');
                window.location.href = '/login';
                return;
            }
            if (msg) msg.textContent = data.error || 'Could not link this student record.';
            return;
        }
        if (msg) msg.textContent = 'Linked successfully.';
        loadStudentDashboard();
    } catch (err) {
        console.error('Error linking student record:', err);
        if (msg) msg.textContent = 'Failed to link. Make sure the server is running.';
    }
}

// Renders horizontal profile bars into any container element.
function renderStudentProfileInto(el, data) {
    if (!el) return;
    const bars = [];
    const colorKey = {
        attendance: v => (v >= 80 ? 'low' : v >= 60 ? 'medium' : 'high'),
        gpa: v => (v >= 3 ? 'low' : v >= 2 ? 'medium' : 'high'),
        stress: v => (v >= 7 ? 'high' : v >= 4 ? 'medium' : 'low'),
    };
    if (data.attendance_rate != null) bars.push(['Attendance', Number(data.attendance_rate), 100, 'attendance', Number(data.attendance_rate).toFixed(1) + '%']);
    if (data.gpa != null) bars.push(['GPA', Number(data.gpa), 4, 'gpa', 'GPA ' + Number(data.gpa).toFixed(2)]);
    if (data.stress_index != null) bars.push(['Stress', Number(data.stress_index), 10, 'stress', 'Index ' + Number(data.stress_index).toFixed(1)]);
    if (data.cgpa != null) bars.push(['CGPA', Number(data.cgpa), 4, 'gpa', 'CGPA ' + Number(data.cgpa).toFixed(2)]);
    if (!bars.length) { el.innerHTML = ''; return; }

    el.innerHTML = '<div class="bar-chart">' +
        bars.map(([label, val, max, kind, display]) => {
            const pct = Math.max(0, Math.min(100, (val / max) * 100));
            return `
                <div class="bar-row">
                    <div class="bar-label">${label}</div>
                    <div class="bar-track">
                        <div class="bar-fill ${colorKey[kind](val)}" style="width: ${pct}%">${display}</div>
                    </div>
                </div>
            `;
        }).join('') + '</div>';
}

// --------------------------------------------------------
// Faculty View
// --------------------------------------------------------
async function loadFacultyStudents() {
    const dept = document.getElementById('facultyDept').value;
    const year = document.getElementById('facultyYear').value;
    const tbody = document.getElementById('facultyTableBody');
    tbody.innerHTML = '<tr><td colspan="7" class="loading">Loading...</td></tr>';

    // Renders a number U+2014-style fallback so a single malformed/missing
    // field (or a NaN that slipped out of the API) can never blank the table.
    const num = (v, digits) => (v === null || v === undefined || !isFinite(Number(v)))
        ? '&mdash;'
        : Number(v).toFixed(digits);
    const tierClass = t => (typeof t === 'string' ? t.toLowerCase() : 'medium');

    try {
        const query = `semester=${encodeURIComponent(year)}`;
        const [listRes, summaryRes] = await Promise.all([
            safeFetch(`${API_BASE}/api/faculty/${encodeURIComponent(dept)}?${query}`),
            safeFetch(`${API_BASE}/api/faculty/${encodeURIComponent(dept)}/summary?${query}`),
        ]);
        if (listRes.status === 401 || summaryRes.status === 401) {
            alert('Session expired. Please log in again.');
            window.location.href = '/login';
            return;
        }
        const students = await listRes.json();
        const summary = await summaryRes.json().catch(() => null);

        if (!Array.isArray(students)) {
            tbody.innerHTML = '<tr><td colspan="7" class="loading">Could not load faculty data.</td></tr>';
            return;
        }

        // Stats reflect every student in the selected department/year, not just
        // the top-25 watchlist rows shown below.
        if (summary && !summary.error) {
            document.getElementById('facultyHigh').textContent = summary.high;
            document.getElementById('facultyMedium').textContent = summary.medium;
            document.getElementById('facultyLow').textContent = summary.low;
            document.getElementById('facultyTotal').textContent = summary.at_risk;
        } else {
            const highCount = students.filter(s => s.risk_tier === 'High').length;
            const medCount = students.filter(s => s.risk_tier === 'Medium').length;
            document.getElementById('facultyHigh').textContent = highCount;
            document.getElementById('facultyMedium').textContent = medCount;
            document.getElementById('facultyLow').textContent = 0;
            document.getElementById('facultyTotal').textContent = students.length;
        }

        // Render table
        if (students.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="loading">No at-risk students found</td></tr>';
            return;
        }

        renderFacultyCharts(students, summary);

        tbody.innerHTML = students.map(s => `
            <tr>
                <td><strong>${s.student_id}</strong></td>
                <td>${s.semester || '&mdash;'}</td>
                <td>${num(s.attendance, 1)}%</td>
                <td>${num(s.gpa, 2)}</td>
                <td>${num(s.stress, 1)}</td>
                <td>${num(s.risk_probability, 1)}%</td>
                <td><span class="tier-badge ${tierClass(s.risk_tier)}">${s.risk_tier || 'Unknown'}</span></td>
            </tr>
        `).join('');
    } catch (err) {
        console.error('Error loading faculty data:', err);
        tbody.innerHTML = '<tr><td colspan="7" class="loading">Error loading faculty data. Please refresh or try another filter.</td></tr>';
    }
}

// --------------------------------------------------------
// Admin View
// --------------------------------------------------------
async function loadAdminOverview() {
    try {
        const res = await safeFetch(`${API_BASE}/api/overview`);
        if (res.status === 401) {
            alert('Session expired. Please log in again.');
            window.location.href = '/login';
            return;
        }
        const data = await res.json();

        if (data.error) {
            console.error(data.error);
            document.getElementById('deptChart').innerHTML = '<p class="loading" style="color:var(--text-muted);padding:1.5rem;">Could not load admin overview.</p>';
            document.getElementById('yearChart').innerHTML = '';
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

        // Render tier breakdown (counts, not probabilities)
        const tiers = {};
        ['High', 'Medium', 'Low'].forEach(t => { if (data.risk_distribution && data.risk_distribution[t] != null) tiers[t] = data.risk_distribution[t]; });
        renderBarChart('adminTierChart', tiers, 'primary', v => String(v));
    } catch (err) {
        console.error('Error loading overview:', err);
    }
}

function renderBarChart(containerId, data, colorClass, valueFormat) {
    const container = document.getElementById(containerId);
    if (!data || Object.keys(data).length === 0) {
        container.innerHTML = '<p class="loading" style="color:var(--text-muted);padding:1.5rem;text-align:center;">No data available</p>';
        return;
    }
    const maxVal = Math.max(...Object.values(data), 0.01);
    const fmt = valueFormat || (v => (v * 100).toFixed(1) + '%');

    container.innerHTML = '<div class="bar-chart">' +
        Object.entries(data)
            .sort((a, b) => b[1] - a[1])
            .map(([key, val]) => {
                const pct = (val / maxVal) * 100;
                const display = fmt(val);
                return `
                    <div class="bar-row">
                        <div class="bar-label">${key}</div>
                        <div class="bar-track">
                            <div class="bar-fill ${colorClass}" style="width: ${pct}%">${display}</div>
                        </div>
                    </div>
                `;
            }).join('') +
        '</div>';
}

// At-risk distribution for the selected department/year plus a risk histogram
// of the top-25 watchlist rows currently in the table.
function renderFacultyCharts(students, summary) {
    if (summary && !summary.error) {
        const tiers = {};
        tiers.High = summary.high;
        tiers.Medium = summary.medium;
        tiers.Low = summary.low;
        renderBarChart('facultyTierChart', tiers, 'primary', v => String(v));
    } else {
        renderBarChart('facultyTierChart', {}, 'primary', v => String(v));
    }

    const bins = Array(10).fill(0);
    (students || []).forEach(s => {
        if (s.risk_probability != null) {
            const i = Math.min(9, Math.max(0, Math.floor(Number(s.risk_probability) * 10)));
            bins[i]++;
        }
    });
    const hist = {};
    bins.forEach((count, i) => { hist[`${i * 10}–${i * 10 + 10}%`] = count; });
    renderBarChart('facultyHistChart', hist, 'primary', v => String(v));
}

// Horizontal bars for the looked-up student: attendance / GPA / stress /
// CGPA, each scaled against its own reference range.
function renderStudentProfile(data) {
    const el = document.getElementById('studentProfileChart');
    if (!el) return;
    const bars = [];
    const colorKey = {
        attendance: v => (v >= 80 ? 'low' : v >= 60 ? 'medium' : 'high'),
        gpa: v => (v >= 3 ? 'low' : v >= 2 ? 'medium' : 'high'),
        stress: v => (v >= 7 ? 'high' : v >= 4 ? 'medium' : 'low'),
    };
    if (data.attendance_rate != null) bars.push(['Attendance', Number(data.attendance_rate), 100, 'attendance', data.attendance_rate.toFixed(1) + '%']);
    if (data.gpa != null) bars.push(['GPA', Number(data.gpa), 4, 'gpa', 'GPA ' + data.gpa.toFixed(2)]);
    if (data.stress_index != null) bars.push(['Stress', Number(data.stress_index), 10, 'stress', 'Index ' + data.stress_index.toFixed(1)]);
    if (data.cgpa != null) bars.push(['CGPA', Number(data.cgpa), 4, 'gpa', 'CGPA ' + data.cgpa.toFixed(2)]);
    if (!bars.length) { el.innerHTML = ''; return; }

    el.innerHTML = '<h4 style="margin-top:1rem;">Student Profile</h4><div class="bar-chart">' +
        bars.map(([label, val, max, kind, display]) => {
            const pct = Math.max(0, Math.min(100, (val / max) * 100));
            return `
                <div class="bar-row">
                    <div class="bar-label">${label}</div>
                    <div class="bar-track">
                        <div class="bar-fill ${colorKey[kind](val)}" style="width: ${pct}%">${display}</div>
                    </div>
                </div>
            `;
        }).join('') + '</div>';
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
