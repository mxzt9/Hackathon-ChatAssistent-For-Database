(function () {
    'use strict';
    const script = document.currentScript;
    const chat = script?.dataset.chat;
    if (!chat) return;
    const origin = new URL(script.src).origin;
    const container = document.createElement('div');
    const root = container.attachShadow({
        mode: 'closed'
    });
    const style = document.createElement('link');
    style.rel = 'stylesheet';
    style.href = origin + '/assets/embed.css';
    const frame = document.createElement('iframe');
    frame.title = 'Чат с базой данных';
    frame.hidden = true;
    frame.setAttribute('referrerpolicy', 'no-referrer');
    const button = document.createElement('button');
    button.textContent = script.dataset.label || 'Задать вопрос';
    button.setAttribute('aria-expanded', 'false');
    button.addEventListener('click', () => {
        if (!frame.src) frame.src = origin + '/widget?chat=' + encodeURIComponent(chat);
        frame.hidden = !frame.hidden;
        button.textContent = frame.hidden ? script.dataset.label || 'Задать вопрос' :
            'Закрыть чат';
        button.setAttribute('aria-expanded', String(!frame.hidden));
    });
    root.append(style, frame, button);
    document.body.appendChild(container);
})();
