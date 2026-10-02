export function createPlayer(elementId, tracks) {
    const root = document.getElementById(elementId);
    const audio = root.querySelector('audio');
    const get = name => root.querySelector(`[data-${name}]`);
    const buttons = [...root.querySelectorAll('[data-track]')];
    const listeners = [];
    let index = 0, loaded = false, finished = false, disposed = false;
    const listen = (target, event, handler) => {
        target.addEventListener(event, handler);
        listeners.push(() => target.removeEventListener(event, handler));
    };
    const time = seconds => {
        if (!Number.isFinite(seconds)) return '0:00';
        const value = Math.max(0, Math.floor(seconds));
        return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, '0')}`;
    };
    const status = text => { get('status').textContent = text; };
    const updateTime = () => {
        get('elapsed').textContent = time(audio.currentTime);
        get('duration').textContent = time(audio.duration);
        get('seek').disabled = !Number.isFinite(audio.duration) || audio.duration <= 0;
        get('seek').value = audio.duration > 0 ? audio.currentTime / audio.duration * 100 : 0;
    };
    const update = () => {
        if (!tracks.length) return;
        get('current-title').textContent = tracks[index].title;
        get('position').textContent = `Áudio ${index + 1} de ${tracks.length}`;
        get('play').disabled = !audio.paused;
        get('pause').disabled = audio.paused;
        buttons.forEach((button, i) => {
            button.classList.toggle('current', i === index);
            if (i === index) button.setAttribute('aria-current', 'true');
            else button.removeAttribute('aria-current');
            button.querySelector('.track-indicator').textContent = i === index && !audio.paused ? '≋' : '▷';
        });
    };
    const load = position => {
        audio.pause(); index = position; finished = false; loaded = true;
        audio.src = tracks[index].url;
        audio.load(); audio.playbackRate = Number(get('speed').value);
        updateTime(); update();
    };
    const play = async () => {
        if (!tracks.length || disposed) return;
        if (finished || !loaded) load(0);
        try { await audio.play(); }
        catch (error) {
            if (!disposed && error.name !== 'AbortError') {
                status(error.name === 'NotAllowedError' ? 'Pressione Play para continuar a reprodução.' : 'Não foi possível reproduzir este áudio. Confira o arquivo ou tente outra seção.');
                update();
            }
        }
    };
    listen(get('play'), 'click', play);
    listen(get('pause'), 'click', () => audio.pause());
    listen(get('stop'), 'click', () => {
        if (!tracks.length) return;
        load(0); status('Parado. Play começa do primeiro áudio.');
    });
    listen(get('speed'), 'change', () => { audio.playbackRate = Number(get('speed').value); });
    listen(get('seek'), 'input', () => {
        if (Number.isFinite(audio.duration)) audio.currentTime = Number(get('seek').value) / 100 * audio.duration;
        updateTime();
    });
    buttons.forEach((button, i) => listen(button, 'click', () => { load(i); void play(); }));
    listen(audio, 'play', () => { update(); status('Reproduzindo.'); });
    listen(audio, 'pause', () => { update(); if (!audio.ended) status('Pausado. Play retoma deste ponto.'); });
    listen(audio, 'waiting', () => status('Carregando áudio…'));
    listen(audio, 'playing', () => status('Reproduzindo.'));
    listen(audio, 'timeupdate', updateTime);
    listen(audio, 'loadedmetadata', updateTime);
    listen(audio, 'error', () => { update(); status('Não foi possível carregar este áudio. Tente novamente ou escolha outra seção.'); });
    listen(audio, 'ended', () => {
        if (index + 1 < tracks.length) { load(index + 1); void play(); }
        else { finished = true; update(); status('Leitura concluída. Play recomeça do primeiro áudio.'); }
    });
    update();
    return { dispose() {
        disposed = true; listeners.forEach(remove => remove());
        audio.pause(); audio.removeAttribute('src'); audio.load();
    }};
}
