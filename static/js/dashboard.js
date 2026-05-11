async function fetchStatus() {
    const response = await fetch("/api/status");
    if (!response.ok) {
        return null;
    }
    return response.json();
}

let lastAlertKey = "";
let alertHideTimer = null;
let statusChart = null;

function playAlertBeep() {
    try {
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (!AudioContextClass) {
            return;
        }

        const audioContext = new AudioContextClass();
        const oscillator = audioContext.createOscillator();
        const gainNode = audioContext.createGain();

        oscillator.type = "sine";
        oscillator.frequency.setValueAtTime(900, audioContext.currentTime);
        gainNode.gain.setValueAtTime(0.04, audioContext.currentTime);

        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);
        oscillator.start();
        oscillator.stop(audioContext.currentTime + 0.2);
    } catch (error) {
        console.debug("Alert beep unavailable:", error);
    }
}

function showLiveAlert(current) {
    const popup = document.getElementById("live-alert-popup");
    const title = document.getElementById("live-alert-title");
    const text = document.getElementById("live-alert-text");
    if (!popup || !title || !text) {
        return;
    }

    const alertTitle = (current.alert_title || "").trim();
    const alertText = (current.alert_text || "").trim();
    if (!alertTitle) {
        popup.classList.remove("show");
        return;
    }

    const alertKey = `${current.vehicle_number || ""}|${current.last_seen || ""}|${alertTitle}|${alertText}`;
    if (alertKey === lastAlertKey) {
        return;
    }
    lastAlertKey = alertKey;

    title.textContent = alertTitle;
    text.textContent = alertText;
    popup.classList.add("show");
    playAlertBeep();

    if (alertHideTimer) {
        clearTimeout(alertHideTimer);
    }
    alertHideTimer = setTimeout(() => {
        popup.classList.remove("show");
    }, 4000);
}

function updateCurrentTime() {
    const clock = document.getElementById("current-time");
    if (!clock) {
        return;
    }
    const now = new Date();
    clock.textContent = now.toLocaleTimeString();
}

function formatStatusBadge(status) {
    const normalized = (status || "UNKNOWN").toUpperCase();
    let statusClass = "neutral";
    if (normalized === "VALID") {
        statusClass = "valid";
    } else if (normalized === "EXPIRED") {
        statusClass = "expired";
    } else if (normalized === "NOT FOUND") {
        statusClass = "notfound";
    }
    return `<span class="status-badge ${statusClass}">${normalized}</span>`;
}

function statusFromExpiryDate(expiryDate) {
    if (!expiryDate) {
        return "UNKNOWN";
    }
    const parsed = new Date(`${expiryDate}T00:00:00`);
    if (Number.isNaN(parsed.getTime())) {
        return "UNKNOWN";
    }
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return parsed < today ? "EXPIRED" : "VALID";
}

function challanStatusLabel(challanRow) {
    const violationText = (challanRow.violation_type || "").toLowerCase();
    if (violationText.includes("expired")) {
        return "EXPIRED";
    }
    return "VIOLATION";
}

function updateStatusChart(stats) {
    const chartCanvas = document.getElementById("status-chart");
    if (!chartCanvas || typeof Chart === "undefined") {
        return;
    }

    const totalVehicles = Number(stats.total_vehicles ?? 0);
    const expiredVehicles = Number(stats.expired_rc ?? 0);
    const validVehicles = Math.max(totalVehicles - expiredVehicles, 0);
    const dataset = [validVehicles, expiredVehicles];

    if (!statusChart) {
        statusChart = new Chart(chartCanvas, {
            type: "pie",
            data: {
                labels: ["VALID", "EXPIRED"],
                datasets: [
                    {
                        data: dataset,
                        backgroundColor: ["rgba(61, 210, 196, 0.8)", "rgba(255, 123, 114, 0.82)"],
                        borderColor: ["rgba(61, 210, 196, 1)", "rgba(255, 123, 114, 1)"],
                        borderWidth: 1,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        labels: {
                            color: "#e8f4ff",
                            font: { size: 12 },
                        },
                    },
                },
            },
        });
        return;
    }

    statusChart.data.datasets[0].data = dataset;
    statusChart.update();
}

function updateDashboard(data) {
    if (!data) {
        return;
    }

    const current = data.current;
    const stats = data.stats;

    const text = (id, value) => {
        const element = document.getElementById(id);
        if (element) {
            element.textContent = value ?? "-";
        }
    };

    text("vehicle-number", current.vehicle_number);
    text("owner-name", current.owner_name);
    text("vehicle-model", current.vehicle_model);
    text("rc-expiry", current.rc_expiry_date);
    text("fine-amount", `INR ${current.fine_amount ?? 0}`);
    text("location", current.location);
    text("challan-status", current.challan_status ?? "No challan generated");
    text("stat-vehicles", stats.total_vehicles);
    text("stat-violations", stats.total_violations ?? stats.total_detections);
    text("stat-challans", stats.total_challans);

    const status = document.getElementById("rc-status");
    if (status) {
        status.textContent = current.rc_status;
        status.className = "status-pill";
        if (current.rc_status === "VALID") {
            status.classList.add("valid");
        } else if (current.rc_status === "EXPIRED") {
            status.classList.add("expired");
        } else if (current.rc_status === "NOT FOUND") {
            status.classList.add("notfound");
        } else {
            status.classList.add("neutral");
        }
    }

    const message = document.getElementById("detection-message");
    if (message) {
        const notFound = current.rc_status === "NOT FOUND";
        message.textContent = notFound ? "Vehicle not found in database" : current.message;
        message.className = `alert ${(current.violation || notFound) ? "alert-danger" : "alert-secondary"} mt-3 mb-0`;
    }

    showLiveAlert(current);
    updateStatusChart(stats);

    const snapshotImage = document.getElementById("snapshot-image");
    const snapshotEmpty = document.getElementById("snapshot-empty");
    if (snapshotImage && snapshotEmpty) {
        if (current.snapshot_url) {
            snapshotImage.src = `${current.snapshot_url}?t=${Date.now()}`;
            snapshotImage.classList.remove("d-none");
            snapshotEmpty.classList.add("d-none");
        } else {
            snapshotImage.classList.add("d-none");
            snapshotImage.removeAttribute("src");
            snapshotEmpty.classList.remove("d-none");
        }
    }

    const challanCard = document.getElementById("challan-card");
    if (challanCard) {
        if (current.challan) {
            challanCard.classList.remove("empty-state");
            challanCard.innerHTML = `
                <p><strong>Vehicle:</strong> ${current.challan.vehicle_number}</p>
                <p><strong>Owner:</strong> ${current.challan.owner_name}</p>
                <p><strong>Violation:</strong> ${current.challan.violation_type}</p>
                <p><strong>Fine Amount:</strong> INR ${current.challan.fine_amount}</p>
                <p><strong>Timestamp:</strong> ${current.challan.timestamp}</p>
            `;
        } else {
            challanCard.classList.add("empty-state");
            challanCard.textContent = "No challan generated yet.";
        }
    }

    const downloadButton = document.getElementById("download-challan");
    if (downloadButton) {
        if (current.download_url) {
            downloadButton.href = current.download_url;
            downloadButton.classList.remove("d-none");
            downloadButton.textContent = current.download_name
                ? `Download ${current.download_name}`
                : "Download Challan";
        } else {
            downloadButton.classList.add("d-none");
            downloadButton.href = "#";
        }
    }

    const alertCard = document.getElementById("expired-alert");
    if (alertCard) {
        if (current.violation) {
            alertCard.classList.remove("empty-state");
            alertCard.innerHTML = `
                <div class="alert-box alert-box-danger">
                    <h5 class="mb-2">RC EXPIRED</h5>
                    <p class="mb-1">Digital Challan Generated</p>
                    <p class="mb-0">Fine: INR ${current.fine_amount}</p>
                </div>
            `;
        } else {
            alertCard.classList.add("empty-state");
            alertCard.textContent = "No active expired RC alert.";
        }
    }

    const historyBody = document.getElementById("history-table");
    if (historyBody) {
        historyBody.innerHTML = data.history
            .map((row) => `
                <tr>
                    <td>${row.id}</td>
                    <td>${row.vehicle_number}</td>
                    <td>${row.timestamp}</td>
                    <td>${formatStatusBadge(row.rc_status)}</td>
                    <td>${row.image_path || "-"}</td>
                </tr>`)
            .join("");
    }

    const recentChallans = document.getElementById("recent-challans-table");
    if (recentChallans) {
        recentChallans.innerHTML = data.challans
            .map((row) => `
                <tr>
                    <td>${row.vehicle_number}</td>
                    <td>INR ${row.fine_amount}</td>
                    <td>${row.timestamp}</td>
                    <td>${formatStatusBadge(challanStatusLabel(row))}</td>
                </tr>`)
            .join("");
    }

    const vehicleBody = document.getElementById("vehicle-db-table");
    if (vehicleBody) {
        vehicleBody.innerHTML = data.vehicles
            .map((row) => `
                <tr>
                    <td>${row.vehicle_number}</td>
                    <td>${row.owner_name}</td>
                    <td>${row.rc_expiry_date}</td>
                    <td>${formatStatusBadge(statusFromExpiryDate(row.rc_expiry_date))}</td>
                </tr>`)
            .join("");
    }

    const challanTable = document.getElementById("challan-table");
    if (challanTable) {
        challanTable.innerHTML = data.challans
            .map((row) => `
                <tr>
                    <td>${row.id}</td>
                    <td>${row.vehicle_number}</td>
                    <td>${row.owner_name}</td>
                    <td>${row.violation_type} ${formatStatusBadge(challanStatusLabel(row))}</td>
                    <td>INR ${row.fine_amount}</td>
                    <td>${row.timestamp}</td>
                </tr>`)
            .join("");
    }
}

async function refreshLoop() {
    const data = await fetchStatus();
    updateDashboard(data);
}

refreshLoop();
setInterval(refreshLoop, 3000);
updateCurrentTime();
setInterval(updateCurrentTime, 1000);
