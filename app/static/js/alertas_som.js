/**
 * Módulo de som para alertas — compartilhado entre dashboard de alertas e view de dashboards.
 * Gera tons via Web Audio API (sem arquivos de áudio externos).
 */
window.AlertaSom = (function () {
    function playSom(id) {
        if (!id || id === 'none') return;
        try {
            var Ctx = window.AudioContext || window.webkitAudioContext;
            if (!Ctx) return;
            var ctx = new Ctx();
            function beep(freq, start, dur) {
                var o = ctx.createOscillator();
                var g = ctx.createGain();
                o.connect(g);
                g.connect(ctx.destination);
                o.frequency.value = freq;
                o.type = 'sine';
                g.gain.value = 0.25;
                o.start(ctx.currentTime + start);
                o.stop(ctx.currentTime + start + dur);
            }
            if (id === 'beep') beep(800, 0, 0.25);
            else if (id === 'beep2') { beep(800, 0, 0.15); beep(800, 0.25, 0.15); }
            else if (id === 'alert') beep(1000, 0, 0.4);
            else if (id === 'notification') { beep(660, 0, 0.1); beep(880, 0.15, 0.1); beep(1100, 0.3, 0.15); }
            else if (id === 'urgente') { beep(600, 0, 0.1); beep(800, 0.12, 0.1); beep(1000, 0.24, 0.1); beep(800, 0.36, 0.15); }
            else beep(800, 0, 0.25);
        } catch (e) { /* AudioContext not available */ }
    }
    return { playSom: playSom };
})();
