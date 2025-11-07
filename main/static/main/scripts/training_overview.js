// Load previous training sessions and render latest on page load
(function(){
  async function fetchJSON(url){
    const r = await fetch(url, {headers:{'X-Requested-With':'XMLHttpRequest'}});
    return r.json();
  }

  function populateSessions(items){
    const sel = document.getElementById('train-session-select');
    if (!sel) return null;
    sel.innerHTML = '';
    (items||[]).forEach(it => {
      const opt = document.createElement('option');
      opt.value = it.id;
      opt.textContent = `${it.date} • ${it.model_name.toUpperCase()} • ${it.round_count}/${it.max_rounds}`;
      sel.appendChild(opt);
    });
    return sel;
  }

  function renderAccuracy(rounds, accuracies){
    if (!window.TrainingProgressChart) return;
    const maxRound = rounds && rounds.length ? Math.max(...rounds) + 1 : 10;
    TrainingProgressChart.reset(maxRound);
    (rounds||[]).forEach((r, idx) => {
      const acc = accuracies[idx];
      if (acc != null) TrainingProgressChart.addAccuracyPoint(r+1, acc);
    });
  }

  async function loadTrain(trainId){
    try{
      const info = await fetchJSON(`/training/rounds/?train_id=${trainId}`);
      if (info && info.success){
        renderAccuracy(info.rounds, info.accuracies);
        // load confusion for last available round
        const lastIdx = (info.accuracies||[]).map((v,i)=>v!=null?i:null).filter(v=>v!=null).pop();
        const roundNo = (lastIdx!=null) ? lastIdx : (info.rounds||[]).slice(-1)[0] || 0;
        const conf = await fetchJSON(`/training/confusion/?train_id=${trainId}&round=${roundNo}`);
        if (conf && conf.success && Array.isArray(conf.confusion)){
          if (window.renderConfusionMatrix) {
            window.renderConfusionMatrix(conf.confusion, conf.classes||[], conf.support||[]);
          }
        }
      }
    }catch(e){ /* noop */ }
  }

  async function init(){
    try{
      const data = await fetchJSON('/training/trains/');
      if (!data || !data.success) return;
      const sel = populateSessions(data.items);
      if (sel && sel.options.length){
        const first = sel.options[0].value;
        await loadTrain(first);
        sel.addEventListener('change', ev => loadTrain(ev.target.value));
      }
    }catch(e){ /* noop */ }
  }

  if (document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', init);
  } else { init(); }
})();

