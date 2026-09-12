/* Intervention platform: create, list, update status, delete. */
let interventionsRole = null;

async function fetchInterventions() {
  const params = new URLSearchParams();
  const status = document.getElementById('intFilterStatus')?.value;
  const term = document.getElementById('intSearch')?.value.trim();
  if (status) params.set('status', status);
  if (term) params.set('term', term);
  const res = await fetch('/api/interventions?' + params.toString());
  if (res.status === 403) {
    document.getElementById('interventionsBody').innerHTML =
      '<tr class="loading"><td colspan="8">Not allowed to view interventions.</td></tr>';
    return [];
  }
  const data = await res.json();
  return (data.interventions || []);
}

async function loadInterventions() {
  const body = document.getElementById('interventionsBody');
  body.innerHTML = '<tr class="loading"><td colspan="8">Loading interventions...</td></tr>';
  let items = [];
  try {
    items = await fetchInterventions();
  } catch (e) {
    body.innerHTML = '<tr class="loading"><td colspan="8">Error loading interventions.</td></tr>';
    return;
  }

  if (items.length === 0) {
    body.innerHTML = '<tr class="loading"><td colspan="8">No interventions found.</td></tr>';
  } else {
    body.innerHTML = items.map(renderInterventionRow).join('');
  }

  const count = (s) => items.filter((i) => i.status === s).length;
  document.getElementById('intTotal').textContent = items.length;
  document.getElementById('intOpen').textContent = count('Open');
  document.getElementById('intInProgress').textContent = count('In Progress');
  document.getElementById('intResolved').textContent = count('Resolved');
}

function renderInterventionRow(item) {
  const tierClass = {
    Open: 'badge-danger',
    'In Progress': 'badge-warning',
    Resolved: 'badge-success',
  }[item.status] || '';

  const statusSelect =
    '<select class="int-status" data-id="' + item.id + '" onchange="updateInterventionStatus(this)">' +
    ['Open', 'In Progress', 'Resolved'].map((s) =>
      '<option value="' + s + '"' + (item.status === s ? ' selected' : '') + '>' + s + '</option>'
    ).join('') +
    '</select>';

  const deleteBtn =
    interventionsRole === 'admin'
      ? '<button class="btn btn-danger" onclick="deleteIntervention(' + item.id + ')">Delete</button>'
      : '<span class="text-muted" style="font-size:0.78rem;">&mdash;</span>';

  return (
    '<tr>' +
    '<td>' + item.id + '</td>' +
    '<td><strong>#' + item.student_id + '</strong><br><span class="text-muted" style="font-size:0.8rem;">' +
    escapeHtml(item.student_name || '-') + '</span></td>' +
    '<td>' + escapeHtml(item.intervention_type) + '</td>' +
    '<td><span class="tier-badge ' + tierClass + '">' + item.status + '</span></td>' +
    '<td style="max-width:220px;">' + escapeHtml(item.description || '-') + '</td>' +
    '<td>' + escapeHtml(item.created_by || '-') + '</td>' +
    '<td style="font-size:0.8rem; color:var(--text-muted);">' + escapeHtml(item.created_at || '') + '</td>' +
    '<td style="white-space:nowrap;">' + statusSelect + ' ' + deleteBtn + '</td>' +
    '</tr>'
  );
}

async function createIntervention(event) {
  const studentId = document.getElementById('intStudentId').value;
  const payload = {
    student_id: studentId,
    student_name: document.getElementById('intStudentName').value.trim(),
    intervention_type: document.getElementById('intType').value,
    description: document.getElementById('intDescription').value.trim(),
  };

  const res = await fetch('/api/interventions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) {
    alert('Error: ' + (data.error || 'Could not create intervention.'));
    return false;
  }
  document.getElementById('intForm').reset();
  document.getElementById('intType').selectedIndex = 0;
  loadInterventions();
  return false;
}

async function updateInterventionStatus(select) {
  const res = await fetch('/api/interventions/' + select.dataset.id, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status: select.value }),
  });
  const data = await res.json();
  if (!res.ok) {
    alert('Error: ' + (data.error || 'Could not update status.'));
  }
  loadInterventions();
}

async function deleteIntervention(id) {
  if (!confirm('Delete intervention #' + id + '?')) return;
  const res = await fetch('/api/interventions/' + id, { method: 'DELETE' });
  if (res.status === 403) {
    alert('Only admins can delete interventions.');
    return;
  }
  loadInterventions();
}

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function initInterventions(role) {
  interventionsRole = role;
  loadInterventions();
}