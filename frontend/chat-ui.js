(function (root) {
    'use strict';
    const escape = (value) => String(value ?? '').replace(/[&<>"']/g, (character) => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
    })[character]);

    function resultTable(table) {
        const headers = table.fields.map(field => `<th>${escape(field)}</th>`).join('');
        const rows = table.rows.map(row => {
            const cells = row.map(value => {
                const text = typeof value === 'object' && value !== null ? JSON.stringify(value) : value;
                return `<td>${escape(text)}</td>`;
            }).join('');
            return `<tr>${cells}</tr>`;
        }).join('');
        const empty = `<tr><td colspan="${Math.max(1, table.fields.length)}">Данных не найдено.</td></tr>`;
        return `
            <div class="result-scroll" tabindex="0">
                <table>
                    <thead><tr>${headers}</tr></thead>
                    <tbody>${rows || empty}</tbody>
                </table>
            </div>`;
    }

    function sqlDetails(sql, meta) {
        const explain = meta.explain || {};
        const engine = meta.engine === 'university' ? 'университетский генератор' : 'модель';
        const lines = [
            `<p>SQL: ${engine}</p>`,
            `<p>Таблицы: ${escape((explain.tables || []).join(', '))}</p>`
        ];
        for (const [key, label] of [
                ['joins', 'Связи'],
                ['filters', 'Фильтры'],
                ['aggregates', 'Агрегаты']
            ]) {
            if (explain[key]?.length) lines.push(`<p>${label}: ${escape(explain[key].join('; '))}</p>`);
        }
        lines.push(`<p>Лимит: ${escape(explain.limit)} · ${escape(meta.total_ms || 0)} мс</p>`);
        return `
            <details class="sql-details">
                <summary>SQL и объяснение запроса</summary>
                <pre><code>${escape(sql)}</code></pre>
                ${lines.join('')}
            </details>`;
    }

    function content(message) {
        let html = `<p>${escape(message.text)}</p>`;
        if (message.table) html += resultTable(message.table);
        if (message.sql) html += sqlDetails(message.sql, message.meta || {});
        return html;
    }
    root.ChatUI = {
        escape,
        content
    };
})(window);
