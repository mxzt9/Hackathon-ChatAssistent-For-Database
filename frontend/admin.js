(async function () {
    'use strict';
    const escape = ChatUI.escape;
    let database;
    const status = document.getElementById('connection-status');
    async function request(path, options = {}) {
        const response = await fetch('/api' + path, {
            credentials: 'omit',
            headers: {
                'Content-Type': 'application/json'
            },
            ...options
        });
        const result = await response.json();
        if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Проверьте введённые данные.');
        return result;
    }

    function columnOption(table, column) {
        const labels = {
            forbidden: 'Закрыто',
            aggregate_only: 'Только агрегаты',
            public: 'Можно выводить'
        };
        const checked = table.fields.includes(column.name) ? 'checked' : '';
        const disabled = !table.enabled || column.level === 'forbidden' ? 'disabled' : '';
        return `
            <label class="column-option">
                <input type="checkbox" data-field="${escape(column.name)}"
                       data-level="${escape(column.level)}" ${checked} ${disabled}>
                <span>${escape(column.name)}
                    <small>${escape(column.type)} · ${labels[column.level]}</small>
                </span>
            </label>`;
    }

    function tableOptions(table) {
        const checked = table.enabled ? 'checked' : '';
        return `
            <fieldset class="table-access" data-table="${escape(table.name)}">
                <legend>
                    <label><input type="checkbox" data-enable-table
                                  value="${escape(table.name)}" ${checked}> ${escape(table.name)}</label>
                </legend>
                <div class="column-list">
                    ${table.columns.map(column => columnOption(table, column)).join('')}
                </div>
            </fieldset>`;
    }

    function selectedAccess() {
        const tables = [];
        const fields = {};
        document.querySelectorAll('#connection-tables fieldset').forEach(table => {
            if (table.querySelector('[data-enable-table]').checked) tables.push(table.dataset.table);
            fields[table.dataset.table] = Array.from(
                table.querySelectorAll('[data-field]:checked'), input => input.dataset.field
            );
        });
        return {
            tables,
            fields,
            version: database.version
        };
    }

    function render() {
        document.getElementById('access-step').hidden = false;
        document.getElementById('connection-tables').innerHTML = database.tables.map(tableOptions).join('');
        const management = location.origin + '/setup/' + encodeURIComponent(database.id);
        document.getElementById('management-link').value = management;
        history.replaceState(null, '', '/setup/' + encodeURIComponent(database.id));
        document.getElementById('connection-step').hidden = true;
        document.getElementById('share-step').hidden = !database.published;
        if (!database.published) return;
        const publicId = encodeURIComponent(database.public_id);
        const link = location.origin + '/chat/' + publicId;
        document.getElementById('chat-link').value = link;
        document.getElementById('open-chat').href = link;
        document.getElementById('iframe-code').value =
            `<iframe src="${location.origin}/widget?chat=${publicId}" title="Чат-ассистент" width="440" height="680" style="border:0"></iframe>`;
        document.getElementById('button-code').value = '<script src="' + location.origin +
            '/assets/embed.js" data-chat="' + database.public_id + '" defer><' + '/script>';
    }
    document.getElementById('connection-form').onsubmit = async event => {
        event.preventDefault();
        const button = event.target.querySelector('button');
        button.disabled = true;
        status.textContent = 'Проверяем подключение…';
        try {
            const values = Object.fromEntries(new FormData(event.target));
            values.port = Number(values.port);
            database = await request('/connections', {
                method: 'POST',
                body: JSON.stringify(values)
            });
            event.target.elements.password.value = '';
            status.textContent = '';
            render();
        } catch (error) {
            status.textContent = error.message;
        } finally {
            button.disabled = false;
        }
    };
    document.getElementById('connection-tables').onchange = event => {
        if (!event.target.matches('[data-enable-table]')) return;
        event.target.closest('fieldset').querySelectorAll('[data-field]').forEach(
            input => input.disabled = !event.target.checked || input.dataset.level === 'forbidden');
    };
    document.getElementById('select-safe').onclick = () => {
        document.querySelectorAll('#connection-tables fieldset').forEach(table => {
            table.querySelector('[data-enable-table]').checked = true;
            table.querySelectorAll('[data-field]').forEach(input => {
                input.checked = input.dataset.level !== 'forbidden';
                input.disabled = input.dataset.level === 'forbidden';
            });
        });
    };
    document.getElementById('connection-access').onsubmit = async event => {
        event.preventDefault();
        const button = event.target.querySelector('[type=submit]');
        button.disabled = true;
        const message = document.getElementById('access-status');
        try {
            database = await request('/connections/' + encodeURIComponent(database.id) + '/whitelist', {
                method: 'PUT',
                body: JSON.stringify(selectedAccess())
            });
            message.textContent = 'Ссылка готова. Настройки доступа применены.';
            render();
        } catch (error) {
            message.textContent = error.message;
        } finally {
            button.disabled = false;
        }
    };
    document.getElementById('copy-chat').onclick = async () => {
        try {
            await navigator.clipboard.writeText(document.getElementById('chat-link').value);
            document.getElementById('share-status').textContent =
                'Ссылка скопирована.';
        } catch {
            document.getElementById('chat-link').select();
            document.getElementById('share-status').textContent =
                'Скопируйте выделенную ссылку.';
        }
    };
    document.getElementById('remove-chat').onclick = async () => {
        try {
            await request('/connections/' + encodeURIComponent(database.id), {
                method: 'DELETE'
            });
            location.href = '/';
        } catch (error) {
            document.getElementById('share-status').textContent = error.message;
        }
    };
    const adminId = location.pathname.startsWith('/setup/') ? location.pathname.slice(
        '/setup/'.length) : null;
    if (adminId) {
        try {
            database = await request('/connections/' + encodeURIComponent(adminId));
            render();
        } catch (error) {
            status.textContent = error.message + ' Создайте подключение заново.';
        }
    }
})();
