function createModal(message, type, callback) {
  
  const existing = document.getElementById('customModal');
  if (existing) existing.remove();

  
  const modal = document.createElement('div');
  modal.id = 'customModal';
  modal.style.position = 'fixed';
  modal.style.inset = '0';
  modal.style.display = 'flex';
  modal.style.justifyContent = 'center';
  modal.style.alignItems = 'center';
  modal.style.background = 'rgba(0,0,0,0.5)';
  modal.style.zIndex = '9999';

  
  const box = document.createElement('div');
  box.className = 'diacard';
 
  
 
  

  const msg = document.createElement('h3');
  msg.textContent = message;
  msg.textContent.color = "#fff";
 
  

  
  const btnGroup = document.createElement('div');
  btnGroup.style.display = 'flex';
  btnGroup.style.justifyContent = 'center';
  btnGroup.style.gap = '10px';

 
  const okBtn = document.createElement('button');
  okBtn.textContent = type === 'alert' ? 'OK' : 'Yes';
  okBtn.style.background = '#fff'
  okBtn.style.color = '#000';
  okBtn.style.border = 'none';
  okBtn.style.padding = '10px 18px';
  okBtn.style.borderRadius = '6px';
  okBtn.style.cursor = 'pointer';

  okBtn.onclick = () => {
    modal.remove();
    if (callback) callback(true);
  };

  btnGroup.appendChild(okBtn);

  
  if (type === 'confirm') {
    const cancelBtn = document.createElement('button');
    cancelBtn.textContent = 'Cancel';
    cancelBtn.style.background = 'Transparent';
    cancelBtn.style.color = 'white';
    cancelBtn.style.border = ' 1px solid rgb(255, 255, 255)';
    cancelBtn.style.padding = '10px 18px';
    cancelBtn.style.borderRadius = '6px';
    cancelBtn.style.cursor = 'pointer';

    cancelBtn.onclick = () => {
      modal.remove();
      if (callback) callback(false);
    };

    btnGroup.appendChild(cancelBtn);
  }

  box.appendChild(msg);
  box.appendChild(btnGroup);
  modal.appendChild(box);
  document.body.appendChild(modal);
}


function alertCustom(message) {
  createModal(message, 'alert', null);
}


function confirmCustom(message, callback) {
  createModal(message, 'confirm', callback);
}


