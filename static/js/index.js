let currentSessionId = null;

        async function createSession() {
            const adminName = document.getElementById('admin-name').value.trim();
            const sessionName = document.getElementById('session-name').value.trim();

            if (!adminName || !sessionName) {
                alert('Please fill in both fields.');
                return;
            }

            const response = await fetch('/create_session', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ admin_name: adminName, session_name: sessionName })
            });

            const data = await response.json();
            currentSessionId = data.session_id;

            document.getElementById('session-id-display').textContent = data.session_id;
            document.getElementById('join-link-display').textContent = data.join_url;
            document.getElementById('session-result').style.display = 'block';
        }

        function copyLink() {
            const link = document.getElementById('join-link-display').textContent;
            navigator.clipboard.writeText(link);
            alert('Link copied!');
        }

        function goToDashboard() {
            if (currentSessionId) {
                window.location.href = `/dashboard/${currentSessionId}`;
            }
        }