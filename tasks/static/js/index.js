let lastDraggableItem = null;
let lastClickedKanbanModal = null;
let activeIntervals = {};
const toastEl = document.getElementById('liveToast');
const toastTimerEl = document.getElementById('toastTimer');
let startTime = 3000; // 3 секунды в миллисекундах
let timerInterval;
let remainingTime = startTime;
let lastClickedTimer = [0,0,0];
let lastKanbanObserver = null;
let toastHideTimeout = null; // id setTimeout для автоскрытия
let currentLastKanbanElement = null;
const PLAY_SELECTOR = '[data-action="play"], #playButton';

let monthObserver = null;
let scrollHandlerTimeout = null;

window.onload = (e) => {
    const scrollBlocks = document.querySelectorAll(".row.flex-nowrap.overflow-x-scroll");
    let isDraggingScroll = false;
    let startX, scrollLeft;
    let currentBlock = null;
    let isSyncing = false;

    document.addEventListener('submit', (e) => {
        const form = e.target;
        if (!(form instanceof HTMLFormElement)) return;
        if (form.hasAttribute('data-native')) return; // позволить обычный submit, если нужно
        e.preventDefault();
        e.stopPropagation();
    });

    // Глобальные обработчики для скролла
    const handleScrollMove = (e) => {
        if (!isDraggingScroll || !currentBlock) return;
        
        e.preventDefault();
        const x = e.pageX || (e.touches && e.touches[0].pageX);
        const walk = (x - startX) * 1;
        currentBlock.scrollLeft = scrollLeft - walk;
        syncScroll(currentBlock.scrollLeft);
    };

    const handleScrollEnd = () => {
        if (!isDraggingScroll) return;
        isDraggingScroll = false;
        if (currentBlock) {
            currentBlock.style.cursor = 'grab';
            currentBlock.style.userSelect = 'auto';
        }
        removeScrollListeners();
    };

    const addScrollListeners = () => {
        document.addEventListener('mousemove', handleScrollMove);
        document.addEventListener('touchmove', handleScrollMove);
        document.addEventListener('mouseup', handleScrollEnd);
        document.addEventListener('touchend', handleScrollEnd);
    };

    const removeScrollListeners = () => {
        document.removeEventListener('mousemove', handleScrollMove);
        document.removeEventListener('touchmove', handleScrollMove);
        document.removeEventListener('mouseup', handleScrollEnd);
        document.removeEventListener('touchend', handleScrollEnd);
    };

    // Отдельная система для kanban-элементов
    let kanbanItems = document.querySelectorAll('.kanban-item');
    if (kanbanItems.length == 0) {
        kanbanItems = document.querySelectorAll('.card.shadow.mb-3')
    }
    kanbanItems.forEach(item => {
        item.addEventListener('mousedown', () => {
            lastDraggableItem = item;

            // При начале drag kanban-элемента принудительно завершаем скролл
            if (isDraggingScroll) {
                handleScrollEnd();
            }
        });
    });
    // let timer = null
    // for (let a in activeTimers) {
    //     for (let kan in kanbanItems) {
    //         if (kan.id == a) {
    //             timer = kan.querySelector(".col-auto.text-secondary small")
    //         }
    //     }
    // }
    // if (timer == null) {
    //     let cards = document.querySelectorAll(".card.shadow mb-3")
    //     for (let a in activeTimers) {
    //         for (let card in cards) {
    //             if  (card.id == a) {
    //                 timer = card.querySelector(".col-auto.text-secondary small")
    //             }
    //         }
    //     }
    // }

    // Пока бесполезно

    const syncScroll = (scrollValue) => {
        if (isSyncing) return;
        isSyncing = true;
        scrollBlocks.forEach(block => {
            if (block !== currentBlock) {
                block.scrollLeft = scrollValue;
            }
        });
        isSyncing = false;
    };

    scrollBlocks.forEach(block => {
        block.addEventListener('mousedown', (e) => {
            // Игнорируем если кликнули на kanban-элемент
            if (e.target.closest('.kanban-item')) return;
            console.log(e)
            isDraggingScroll = true;
            currentBlock = block;
            startX = e.pageX - block.offsetLeft;
            scrollLeft = block.scrollLeft;
            block.style.cursor = 'grabbing';
            block.style.userSelect = 'none';
            
            addScrollListeners();
        });

        block.addEventListener('touchstart', (e) => {
            if (e.target.closest('.kanban-item')) return;
            
            isDraggingScroll = true;
            currentBlock = block;
            startX = e.touches[0].pageX - block.offsetLeft;
            scrollLeft = block.scrollLeft;
            addScrollListeners();
        });

        block.addEventListener('scroll', (e) => {
            if (!isDraggingScroll) {
                currentBlock = null;
                syncScroll(block.scrollLeft);
            }
        })

        block.style.cursor = 'grab';
    });

    // Изменить текст modal для splitTask
    document.querySelector("#rangeTaskTimeHours").addEventListener('input', (e) => {
        const modal = document.querySelector('#modalTaskSplit')
        let minutes = document.querySelector('#rangeTaskTimeMinutes');
        let sumTime = 0;
        if (e.target.value != '') {
            sumTime += parseInt(e.target.value)*60
        }
        if (minutes.value != '') {
            sumTime += parseInt(minutes.value)
        }
        modal.querySelector('.form-label').textContent = "Выделено " + returnCorrectTime(sumTime);
    })

    document.querySelector("#rangeTaskTimeMinutes").addEventListener('input', (e) => {
        const modal = document.querySelector('#modalTaskSplit')
        let hours = document.querySelector('#rangeTaskTimeHours');
        let sumTime = 0;
        if (e.target.value != '') {
            sumTime += parseInt(e.target.value);
        }
        if  (hours.value != '') {
            sumTime += parseInt(hours.value) * 60;
        }
        modal.querySelector('.form-label').textContent = "Выделено " + returnCorrectTime(sumTime);
    })

    // Закрытие по кнопке modal
    toastEl.querySelector('.btn-close').addEventListener('click', () => {
        hideToast();
    });

    let currentDay = document.querySelector('#inputCurrentDay').value;
    console.log(currentDay);
    let block = document.querySelectorAll(".row.flex-nowrap.overflow-x-scroll.mb-3")[currentDay-1]
    
    // Переход на сегодняшний день
    setTimeout(() => {
        block.scrollIntoView({
            behavior: 'smooth',
            block: 'center'
        });
    }, 300);

    attachPlayDelegationOnce();
    initActiveSelfTimer();
    document.querySelectorAll(`.card.${UNDER_REVIEW_CLASS}`).forEach(applyUnderReviewTheme);
    document
    .querySelectorAll('.card.opacity-50, .card[data-status="completed"]')
    .forEach(applyCompletedTheme);

    for (let timer of activeTimers['all']) {
        for (let kan of kanbanItems) {
            if (kan.id == timer[0]) {
                updateActiveTimers(timer, kan)
            }
        }
    }

    // }
    initMonthObserver()
    // Месяц

    // Дозагрузка календаря
    trackLastKanbanCategory();
    // Дозагрузка календаря

    // делегирование кликов: submit-review / open-review / modal buttons
    document.addEventListener('click', (e) => {
    // 1) Исполнитель отправляет на проверку
        const submitBtn = e.target.closest('[data-action="submit-review"]');
        if (submitBtn) {
            e.preventDefault();
            const card = submitBtn.closest('.kanban-item, .card.shadow.mb-3');
            const localId = card && card.id ? parseInt(card.id, 10) : 0;
            if (!localId) { showToast({status:'error', message:'Не удалось определить задачу'}); return; }

            fetchJsonWithTimeout('/api/submit-review/', {
                method: 'POST',
                headers: { 'X-CSRFToken': getCookie('csrftoken') },
                body: new URLSearchParams({ task_id: String(localId) })
            }, 3000)
            .then(([r, payload]) => {
                console.debug('[submit-review] response:', r, payload);
                if (!r.ok || payload.status !== 'success') {
                const diag = explainErrorTuple(r, payload);
                const msg = (payload && (payload.message || payload.error)) || 'Ошибка отправки на проверку';
                showToast({status:'error', message: `${msg} · ${diag}`});
                return;
                }
                const ids = payload.data?.group_ids || [];
                ids.forEach(id => {
                const node = document.getElementById(String(id));
                if (!node) return;
                const flag = node.querySelector('[data-action="submit-review"]'); if (flag) flag.remove();
                const card = node.querySelector('.card') || node;
                card.classList.add('text-bg-primary');
                applyUnderReviewTheme(card);
                // if (!node.querySelector('[data-action="open-review"]')) {
                //     const dd = node.querySelector('.dropdown');
                //     if (dd) {
                //         const a = document.createElement('a');
                //         a.href = '#'; a.className = 'text-black'; a.style.cssText='font-size:16px; margin-right:5px;';
                //         a.setAttribute('data-action','open-review');
                //         a.innerHTML = '<i class="fe fe-check-square"></i>';
                //         dd.appendChild(a);
                //     }
                // }
                });
                showToast({status:'success', message:'Отправлено на проверку'});
            })
            .catch(err => {
                const msg = (err && err.name === 'AbortError')
                ? 'Таймаут запроса (3с)'
                : `Сетевая/JS ошибка: ${err?.message || err}`;
                console.error('[submit-review] catch:', err);
                showToast({status:'error', message: msg});
            });
            return;
        }

        // 2) Руководитель открывает модалку
        const reviewBtn = e.target.closest('[data-action="open-review"]');
        if (reviewBtn) {
            e.preventDefault();
            const node = reviewBtn.closest('.kanban-item, .card.shadow.mb-3');
            const bitrixId = getBitrixIdFromNode(node || reviewBtn);
            if (!bitrixId) { showToast({status:'error', message:'Нет bitrix_id для проверки'}); return; }
            document.getElementById('reviewBitrixId').value = String(bitrixId);
            let el = document.createElement('a');

            el.setAttribute('data-bs-toggle','modal')
            el.setAttribute('data-bs-target','#modalReview')
            el.setAttribute('aria-haspopup','true')
            el.setAttribute('aria-expanded','false')
            console.log(el)

            document.body.appendChild(el)
            el.click()
            document.body.removeChild(el)
            return;
        }

        // 3) Кнопка закрытия модалки
        const closeBtn = e.target.closest('[data-close="modalReview"]');
        if (closeBtn) { 
            document.querySelectorAll(".btn-close")[2].click()
            return; 
        }

        // 4) Решение: принять/доработка
        const decisionBtn = e.target.closest('[data-review]');
        if (decisionBtn && decisionBtn.closest('#modalReview')) {
            const decision = decisionBtn.getAttribute('data-review'); // 'approve' | 'reject'
            const bitrixId = document.getElementById('reviewBitrixId').value;
            if (!bitrixId) { showToast({status:'error', message:'Нет bitrix_id'}); return; }

            const modal = document.getElementById('modalReview');
            const buttons = modal.querySelectorAll('[data-review]');
            buttons.forEach(b => b.disabled = true);

            fetchJsonWithTimeout('/api/review-decision/', {
                method: 'POST',
                headers: { 'X-CSRFToken': getCookie('csrftoken') },
                body: new URLSearchParams({ decision, bitrix_id: bitrixId })
            }, 3000)
            .then(([r, payload]) => {
                console.debug('[review-decision] response:', r, payload);
                if (!r.ok || payload.status !== 'success') {
                    const diag = explainErrorTuple(r, payload);
                    const msg = (payload && (payload.message || payload.error)) || 'Не удалось применить решение';
                    showToast({status:'error', message: `${msg} · ${diag}`});
                    return;
                }

                const ids = payload.data?.group_ids || [];
                const st  = payload.data?.status || '';
                ids.forEach(id => {
                    const node = document.getElementById(String(id));
                    if (!node) return;
                    const card = node.querySelector('.card') || node;
                    card.classList.remove('text-bg-primary'); // снимаем "на проверке"
                    if (st === 'completed') card.classList.add('opacity-50'); // чисто визуально
                    revertUnderReviewTheme(card);
                    card.classList.remove(UNDER_REVIEW_CLASS);

                    if (st === 'completed') {
                        applyCompletedTheme(card);   // прозрачность + чистка кнопок
                    }
                });

                document.querySelectorAll('.btn-close')[1].click()
                showToast({status:'success', message: (st==='completed' ? 'Задача принята' : 'Отправлено на доработку')});
            })
            .catch((err) => {
                const msg = (err && err.name === 'AbortError')
                ? 'Таймаут запроса (3с)'
                : `Сетевая/JS ошибка: ${err?.message || err}`;
                console.error('[review-decision] catch:', err);
                showToast({status:'error', message: msg});
            })
            .finally(() => {
                buttons.forEach(b => b.disabled = false);
            });

            return;
        }
    });

    // Очистка
    return () => {
        removeScrollListeners();
        kanbanItems.forEach(item => {
            item.removeEventListener('dragstart', () => {});
        });
    };
};

function explainErrorTuple(r, j) {
  if (!r) return 'Нет ответа от fetch';
  const parts = [`HTTP ${r.status}${r.statusText ? ' ' + r.statusText : ''}`];
  if (j && typeof j === 'object') {
    if (j.message) parts.push(`message: ${j.message}`);
    if (j.error) parts.push(`error: ${j.error}`);
    if (j.error_description) parts.push(`desc: ${j.error_description}`);
    if (j.bitrix?.response?.status_code) parts.push(`bitrix: ${j.bitrix.response.status_code}`);
  }
  return parts.join(' · ');
}

const UNDER_REVIEW_CLASS = 'text-bg-primary';

function applyUnderReviewTheme(cardEl) {
  if (!cardEl) return;

  // Заголовок
  const title = cardEl.querySelector('.card-header-title');
  if (title) {
    title.classList.remove('text-black', 'text-secondary');
    title.classList.add('text-white');
  }

  // Блоки времени (факт/план) — делаем белыми, убираем серый
  cardEl.querySelectorAll('.col-auto').forEach(b => {
    if (b.querySelector('small')) {
      b.classList.remove('text-secondary', 'text-black');
      b.classList.add('text-white');
    }
  });

  // Все ссылки в хедере/дропдауне — белыми
  cardEl.querySelectorAll('.card-header a, .dropdown a').forEach(a => {
    a.classList.remove('text-black', 'text-secondary');
    a.classList.add('text-white');
  });
}

function revertUnderReviewTheme(cardEl) {
  if (!cardEl) return;

  // Заголовок — обратно в чёрный
  const title = cardEl.querySelector('.card-header-title');
  if (title) {
    title.classList.remove('text-white');
    title.classList.add('text-black');
  }

  // Блоки времени — обратно в серый
  cardEl.querySelectorAll('.col-auto').forEach(b => {
    if (b.querySelector('small')) {
      b.classList.remove('text-white', 'text-black');
      b.classList.add('text-secondary');
    }
  });

  // Все ссылки — обратно в чёрный
  cardEl.querySelectorAll('.card-header a, .dropdown a').forEach(a => {
    a.classList.remove('text-white');
    a.classList.add('text-black');
  });
}

function applyCompletedTheme(cardEl) {
  if (!cardEl) return;

  // 1) Прозрачность
  cardEl.classList.add('opacity-50');

  // 2) Удаляем все действия кроме ссылки (fe-link)
  const actions = cardEl.querySelectorAll('.dropdown a');
  actions.forEach(a => {
    const i = a.querySelector('i');
    // оставить только fe-link (и сам <a> со ссылкой)
    if (!i || !i.classList.contains('fe') || !i.classList.contains('fe-link')) {
      a.remove();
    }
  });

  // 3) На всякий случай — убрать play-кнопку, если вдруг была не в dropdown
  const play = cardEl.querySelector('[data-action="play"], #playButton');
  if (play) play.remove();
}

function initMonthObserver() {
    // 1. Создаем или обновляем элемент отображения месяца
    const monthElement = document.querySelector('.card-body p.fw-bold');
    if (!monthElement.id) {
        monthElement.id = 'current-month-display';
    }

    // 2. Удаляем старые наблюдатели, если они есть
    if (monthObserver) {
        monthObserver.disconnect();
    }
    if (scrollHandlerTimeout) {
        clearTimeout(scrollHandlerTimeout);
    }

    // 3. Создаем новый наблюдатель
    monthObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                updateMonthDisplay(entry.target.dataset.associatedDate);
            }
        });
    }, {
        threshold: 0.5,
        rootMargin: '0px 0px -50% 0px'
    });

    // 4. Находим все текущие категории и добавляем их в наблюдатель
    const categories = document.querySelectorAll('.kanban-category');
    categories.forEach(category => {
        monthObserver.observe(category);
    });

    // 5. Добавляем обработчик скролла
    window.addEventListener('scroll', handleScroll);
}

/**
 * Обновляет отображение месяца
 */
function updateMonthDisplay(dateString) {
    const date = new Date(dateString);
    const monthNames = [
        "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
        "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
    ];
    
    document.getElementById('current-month-display').textContent = monthNames[date.getMonth()];
}

/**
 * Обработчик скролла с троттлингом
 */
function handleScroll() {
    clearTimeout(scrollHandlerTimeout);
    scrollHandlerTimeout = setTimeout(() => {
        checkCenterElement();
    }, 100);
}

function getBitrixIdFromNode(node) {
  if (!node) return '';
  // 1) ближайший предок с data-bs-bitrix
  const host = node.closest?.('[data-bs-bitrix]') || null;
  if (host) return host.getAttribute('data-bs-bitrix') || '';

  // 2) сам узел (если это .kanban-item)
  const self = node.getAttribute?.('data-bs-bitrix');
  if (self) return self;

  // 3) поиск среди потомков (на случай нестандартной разметки)
  const child = node.querySelector?.('[data-bs-bitrix]');
  if (child) return child.getAttribute('data-bs-bitrix') || '';

  return '';
}


/**
 * Проверяет центральный элемент в viewport
 */
function checkCenterElement() {
    const viewportHeight = window.innerHeight;
    const viewportCenter = window.scrollY + (viewportHeight / 2);
    const categories = document.querySelectorAll('.kanban-category');
    
    let closestElement = null;
    let smallestDistance = Infinity;
    
    categories.forEach(category => {
        const rect = category.getBoundingClientRect();
        const elementCenter = window.scrollY + rect.top + (rect.height / 2);
        const distance = Math.abs(viewportCenter - elementCenter);
        
        if (distance < smallestDistance) {
            smallestDistance = distance;
            closestElement = category;
        }
    });
    
    if (closestElement) {
        updateMonthDisplay(closestElement.dataset.associatedDate);
    }
}

//
function trackLastKanbanCategory() {
    // 1. Находим все текущие kanban-category элементы
    const kanbanCategories = document.querySelectorAll('.row.flex-nowrap.overflow-x-scroll.mb-3');
    
    // 2. Если элементов нет - выходим
    if (kanbanCategories.length === 0) {
        return;
    }
    
    // 3. Получаем последний элемент
    const newLastElement = kanbanCategories[kanbanCategories.length - 1];
    
    // 4. Если последний элемент не изменился - выходим
    if (currentLastKanbanElement === newLastElement) {
        return;
    }
    
    // 5. Если уже есть наблюдатель - отключаем его от старого элемента
    if (lastKanbanObserver && currentLastKanbanElement) {
        lastKanbanObserver.unobserve(currentLastKanbanElement);
    }
    
    // 6. Создаем новый наблюдатель, если его нет
    if (!lastKanbanObserver) {
        lastKanbanObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    console.log('Последний kanban-category виден!');
                    // Здесь можно вызвать функцию загрузки новых данных
                    const lastDate = entry.target.querySelector('.kanban-category').getAttribute('data-associated-date');
                    loadMoreCalendarData(lastDate);
                }
            });
        }, {
            threshold: 0.5,
            rootMargin: '0px 0px 100px 0px'
        });
    }
    
    // 7. Начинаем наблюдать за новым последним элементом
    lastKanbanObserver.observe(newLastElement);
    currentLastKanbanElement = newLastElement;
    
    console.log('Наблюдатель обновлен для нового последнего элемента');
}

function loadMoreCalendarData(lastDate) {
    console.log(`Загрузка данных начиная с ${lastDate}`);
    const postData = {
        date: lastDate
    }
    fetch('/api/load-calendary/', {
        method: "POST",
        headers: {
            'X-CSRFToken': getCookie('csrftoken'),
        },
        body: new URLSearchParams(postData)
    }).then(response => response.json())
    .then(data => {
        console.log(data.data)
        let appendHere = document.querySelectorAll('.card-body.overflow-y-scroll')[1];
        let row = document.querySelector('.row.flex-nowrap.overflow-x-scroll.mb-3');
        console.log(row)
        let kanbanItem = document.querySelector('.kanban-item')
        if (kanbanItem == null) {
            kanbanItem = document.querySelector('.card.shadow.mb-3')
        }

        let keys = [];
        for (let key in data.data.days_in_month) {
            if (data.data.days_in_month.hasOwnProperty(key)) { // Проверка, что свойство принадлежит самому объекту
                keys.push(key);
            }
        }
        console.log(keys)
        for (let key of keys) {
            // console.log(data.data.days_in_month[key])
            let cloneRow = document.importNode(row, true);
            cloneRow.querySelector('.fw-bold.mb-0').textContent = data.data.days_in_month[key].week_day
            let allKanbanCategories = cloneRow.querySelectorAll('.kanban-category');
            for (let kkk of allKanbanCategories) {
                kkk.setAttribute('data-associated-date', data.data.days_in_month[key].full_date)
                if (kkk.children.length > 0) {
                    kkk.innerHTML = ''; // Чистим kanban-category!
                }
                if (data.data.days_in_month[key].tasks != {}) {
                    for (let userId in data.data.days_in_month[key].tasks) {
                        for (let ky in data.data.days_in_month[key].tasks[userId]) {
                            if (userId == kkk.id) {
                                let cloneItem = document.importNode(kanbanItem, true);
                                cloneItem.id = data.data.days_in_month[key].tasks[userId][ky].task_id
                                cloneItem.setAttribute('data-bs-bitrix', data.data.days_in_month[key].tasks[userId][ky].bitrix_id);
                                cloneItem.querySelector('.card-header-title.text-truncate.fw-bold').textContent = data.data.days_in_month[key].tasks[userId][ky].title;
                                cloneItem.querySelectorAll('.col-auto.text-secondary small')[1].textContent = float_to_time(data.data.days_in_month[key].tasks[userId][ky].time)
                                cloneItem.querySelectorAll('.col-auto.text-secondary')[1].setAttribute('data-time', data.data.days_in_month[key].tasks[userId][ky].time)
                                cloneItem.querySelectorAll('.col-auto.text-secondary small')[0].textContent = formatTime(data.data.days_in_month[key].tasks[userId][ky].accumulated_time)
                                kkk.appendChild(cloneItem)
                                console.log(data.data.days_in_month[key].full_date, data.data.days_in_month[key].tasks[userId][ky])
                            }
                        }
                    }
                }
            }
            appendHere.appendChild(cloneRow)
        }
        window.sortable.destroy()
        initMonthObserver();
        reloadScripts();
        trackLastKanbanCategory();
    })


    // После успешной загрузки и добавления новых элементов:
    // trackLastKanbanCategory(); // Вызываем снова для обновления наблюдателя
}


async function fetchJsonWithTimeout(url, options = {}, timeoutMs = 3000) {
  const ctrl = new AbortController();
  const id = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(url, { ...options, signal: ctrl.signal });
    let j = {};
    try { j = await r.json(); } catch (_) {}
    return [r, j];
  } finally {
    clearTimeout(id);
  }
}


function submitSplitTask(num) {
    const modal = document.querySelector('#modalTaskSplit');
    const taskId = String(
        lastClickedKanbanModal?.id ||
        modal?.dataset.taskId ||
        document.querySelector('#modalTaskSplit #inputHidden')?.value || ''
    );
    if (!taskId) {
        showToast({ status: 'error', message: 'Не удалось определить задачу для сплита.' });
        return;
    }
    let s = [['#rangeTaskTimeHours','#rangeTaskTimeMinutes'], ['#emptyTaskTimeHours', '#emptyTaskTimeMinutes']]
    let hours = parseInt(document.querySelector(s[num][0]).value);
    if (Number.isNaN(hours)) {hours = 0}
    let minutes = parseInt(document.querySelector(s[num][1]).value);
    if (Number.isNaN(minutes)) {minutes = 0}
    console.log('Время num = '+num)
    if (num == 1) {
        const modal = document.getElementById('emptyTaskTime');
        const taskId = String(
            modal?.dataset.taskId ||
            document.querySelector('#emptyTaskTime #inputHidden')?.value || ''
        );
        const targetEmployee = String(modal?.dataset.targetEmployee || '');
        const targetDate = String(modal?.dataset.targetDate || '');

        const hours = parseInt(document.getElementById('emptyTaskTimeHours').value || '0', 10);
        const minutes = parseInt(document.getElementById('emptyTaskTimeMinutes').value || '0', 10);
        const totalMinutes = hours * 60 + minutes;

        if (!taskId) { showToast({status:'error', message:'Не удалось определить задачу'}); return; }
        if (!targetEmployee) { showToast({status:'error', message:'Не удалось определить исполнителя'}); return; }
        if (totalMinutes <= 0) { showToast({status:'error', message:'Задайте время больше нуля'}); return; }

        // 1) сначала меняем время (ещё в backlog)
        fetch('/api/change-time/', {
            method: 'POST',
            headers: { 'X-CSRFToken': getCookie('csrftoken') },
            body: new URLSearchParams({ task_id: taskId, time: String(totalMinutes) })
        })
        .then(r => r.json().then(j => [r, j]))
        .then(([r, payload]) => {
            console.log(payload)
            if (!r.ok || payload.status !== 'success') {
            const msg = (payload && (payload.message || payload.error)) || 'Ошибка при изменении времени';
            showToast({ status: 'error', message: msg });
            return Promise.reject(new Error(msg));
            }
            // 2) затем делегируем в цель → autosplit разложит по дням
            return fetch('/api/delegate/', {
            method: 'POST',
            headers: { 'X-CSRFToken': getCookie('csrftoken') },
            body: new URLSearchParams({ task_id: taskId, user_id: targetEmployee, date: targetDate })
            }).then(r => r.json().then(j => [r, j]));
        })
        .then(([r, payload]) => {
            console.log(payload)
            if (!r.ok || payload.status !== 'success') {
            const msg = (payload && (payload.message || payload.error)) || 'Ошибка при делегировании';
            showToast({ status: 'error', message: msg });
            return;
            }
            const returned = payload.data || {};

            // подготовь шаблон и bitrix_id ДО удаления (если надо)
            const templateEl =
            document.getElementById(taskId) ||
            document.querySelector('.kanban-item') ||
            document.querySelector('.card.shadow.mb-3');
            const movedBitrixId = templateEl?.getAttribute('data-bs-bitrix') || '';

            // единая отрисовка
            window.KANBAN.applyPatch(returned, {
                newEmployeeId: String(modal.dataset.targetEmployee || ''),
                templateEl,
                movedBitrixId,
                // для календаря хотим сортировать по времени → передадим нашу вставку
                placeNode: insertCardByTime
            });

            // закрыть модалку и тост
            document.querySelectorAll('.btn-close')[1].click()
            // closeModalById('emptyTaskTime');
            showToast({ status: 'success', message: 'Время задано и задача распределена' });
        })
        .catch(() => {/* ошибки уже показали тостами */});

        return; // не пускаем дальше стандартную ветку
    }


    if (num == 0) {
        const baseCard = lastClickedKanbanModal;
        const baseCat  = baseCard?.closest('.card')?.querySelector('.kanban-category');
        const date     = baseCat?.getAttribute('data-associated-date') || '';

        const postData = { task_id: taskId, time: hours * 60 + minutes, date };
        console.log(postData)

        fetch('/api/split-task/', {
            method: 'POST',
            headers: { 'X-CSRFToken': getCookie('csrftoken') },
            body: new URLSearchParams(postData)
        })
        .then(r => r.json().then(j => [r, j]))
        .then(([r, payload]) => {
            if (!r.ok || payload.status !== 'success') {
                const msg = (payload && (payload.message || payload.error)) || 'Ошибка при разделении задачи';
                showToast({ status: 'error', message: msg });
                return;
            }

            // закрываем модалку
            document.querySelector('.btn-close')?.click();

            // исходная карточка, от неё клонируем новые
            const baseCard = lastClickedKanbanModal;
            const baseCat = baseCard?.closest('.card')?.querySelector('.kanban-category');
            const employeeId = baseCat ? baseCat.id : null;
            const bitrixId = baseCard?.getAttribute('data-bs-bitrix') || '';

            const patch = payload.data || {};

            // единая отрисовка
            window.KANBAN.applyPatch(patch, {
                newEmployeeId: String(employeeId || ''),
                templateEl: baseCard,
                movedBitrixId: bitrixId,
                placeNode: insertCardByTime
            });
        })
        .catch(err => {
            console.error(err);
        });
    }
}

function getTaskContainer(el) {
  return el.closest('.kanban-item, .card.shadow.mb-3');
}
function getTaskIdFrom(el) {
  const c = getTaskContainer(el);
  return c && c.id ? parseInt(c.id, 10) : 0;
}
function setPlayVisual(btn, running) {
  const icon = btn.querySelector('i') || btn;
  if (running) {
    btn.classList.remove('text-black');
    btn.classList.add('text-primary');
    icon.className = 'fe fe-pause';
  } else {
    btn.classList.remove('text-primary', 'text-warning');
    btn.classList.add('text-black');
    icon.className = 'fe fe-play';
  }
}

// Навешиваем один делегированный обработчик на документ
function attachPlayDelegationOnce() {
  if (window.__playDelegationAttached) return;
  window.__playDelegationAttached = true;

  document.addEventListener('click', (e) => {
    const btn = e.target.closest(PLAY_SELECTOR);
    if (!btn) return;

    const clickedTimerId = getTaskIdFrom(btn);
    const icon = btn.querySelector('i') || btn;

    // Нет запущенных → ставим на «старт через тост»
    if (lastClickedTimer[1] === 0) {
      if (lastClickedTimer[0] === 0) {
        showToast({ status: 'timer', message: '' });
        btn.classList.add('text-warning');
        lastClickedTimer[2] = btn;
        lastClickedTimer[0] = clickedTimerId;
        icon.className = 'fe fe-pause';
      }
      return;
    }

    // Уже есть запущенный → клик по текущему = пауза
    if (lastClickedTimer[1] === clickedTimerId) {
      setPlayVisual(btn, false);
      fetch('/api/task-start/', {
        method: 'POST',
        headers: { 'X-CSRFToken': getCookie('csrftoken') },
        body: new URLSearchParams({ task_id: clickedTimerId })
      })
      .then(r => r.json())
      .then(() => {
        let kanbanItems = document.querySelectorAll('.kanban-item');
        if (!kanbanItems.length) kanbanItems = document.querySelectorAll('.card.shadow.mb-3');
        for (const kan of kanbanItems) {
          if (parseInt(kan.id, 10) === lastClickedTimer[1]) stopTimer(kan.id);
        }
        lastClickedTimer[1] = 0;
      })
      .catch(() => setPlayVisual(btn, true));
    } else {
      // Пытаются стартануть другой таймер
      console.error('Действие отклонено! Другой таймер уже запущен.')
    }


    
  });
}

// Проставляем визуал для уже активного таймера пользователя
function initActiveSelfTimer() {
  const arr = (activeTimers && activeTimers['self']) || [];
  if (!arr.length) return;

  lastClickedTimer[1] = arr[0];

  let kanbanItems = document.querySelectorAll('.kanban-item');
  if (!kanbanItems.length) kanbanItems = document.querySelectorAll('.card.shadow.mb-3');

  for (const kan of kanbanItems) {
    if (parseInt(kan.id, 10) === arr[0]) {
      const btn = kan.querySelector(PLAY_SELECTOR);
      if (btn) {
        btn.classList.add('text-primary');
        (btn.querySelector('i') || btn).className = 'fe fe-pause';
      }
      break;
    }
  }
}

function updateActiveTimers(timer, kanbanItem) {
    // Останавливаем предыдущий таймер для этой задачи, если он был
    if (activeIntervals[timer[0]]) {
        clearInterval(activeIntervals[timer[0]]);
    }

    // Запускаем новый интервал
    const intervalId = setInterval(() => {
        const timerEl = kanbanItem.querySelector('.col-auto.text-secondary');
        
        // if (!timerEl) {
        //     clearInterval(intervalId);
        //     delete activeIntervals[timer[0]];
        //     return;
        // }

        // Увеличиваем время на 1 секунду
        timer[1] += 1;
        
        // Обновляем отображение
        timerEl.innerHTML = '<small>'+formatTime(timer[1])+"</small>";
    }, 1000);

    // Сохраняем ID интервала
    activeIntervals[timer[0]] = intervalId;

    return intervalId;
}

async function reloadScripts() {
  const urls = Object.values(window.appConfig.staticUrls || {});
  await Promise.all(urls.map(src => new Promise(res => {
    const s = document.createElement('script'); s.src = src; s.onload = res; document.body.appendChild(s);
  })));
}

function stopTimer(taskId) {
    if (activeIntervals[taskId]) {
        clearInterval(activeIntervals[taskId]);
        delete activeIntervals[taskId];
    }
}

function stopAllTimers() {
    Object.keys(activeIntervals).forEach(taskId => {
        clearInterval(activeIntervals[taskId]);
    });
    activeIntervals = {};
}

// Вспомогательная функция для форматирования времени
function formatTime(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    
    return [
        hours.toString().padStart(2, '0'),
        minutes.toString().padStart(2, '0'),
        secs.toString().padStart(2, '0')
    ].join(':');
}

function showToast(opts = {}) {
  const { status = 'info', message = '', duration } = opts;
  const delay = Number.isFinite(duration) ? duration : startTime;

  // очистка прежних таймеров
  clearTimeout(toastHideTimeout); toastHideTimeout = null;
  clearInterval(timerInterval);   timerInterval = null;

  // подготовка DOM
  toastEl.style.display = 'block';
  // единый базовый класс (можно доп.цвета прикрутить по статусу)
  toastEl.className = 'toast fade bg-solid-white';

  if (status === 'timer') {
    remainingTime = delay;
    // первичный рендер счётчика
    const secs = Math.floor(remainingTime / 1000);
    const ms   = Math.floor((remainingTime % 1000) / 10);
    toastTimerEl.textContent = `Задание начнется через ${secs}:${String(ms).padStart(2,'0')}`;

    // перезапуск CSS-анимации "show"
    toastEl.classList.remove('show'); void toastEl.offsetWidth; toastEl.classList.add('show');

    // тикаем ровно раз в 10ms и гарантированно скрываем в конце
    timerInterval = setInterval(updateTimer, 10);
    toastHideTimeout = setTimeout(hideToast, delay);

  } else {
    // текст для error/success/info
    (toastEl.querySelector('.toast-body') || toastTimerEl).textContent = message;

    // перезапуск анимации
    toastEl.classList.remove('show'); void toastEl.offsetWidth; toastEl.classList.add('show');

    // автоскрытие по заданной длительности
    toastHideTimeout = setTimeout(hideToast, delay);
  }
}


function updateTimer() {
  // если тост уже скрыт — не обновляем
  if (!toastEl.classList.contains('show')) return;

  remainingTime -= 10;
  if (remainingTime < 0) remainingTime = 0;

  const seconds = Math.floor(remainingTime / 1000);
  const milliseconds = Math.floor((remainingTime % 1000) / 10);
  toastTimerEl.textContent = `Задание начнется через ${seconds}:${String(milliseconds).padStart(2,'0')}`;

  if (remainingTime === 0) {
    clearInterval(timerInterval); timerInterval = null;

    // логика старта таймера задачи — оставил твою как есть
    lastClickedTimer[1] = lastClickedTimer[0];
    lastClickedTimer[0] = 0;
    if (lastClickedTimer[2]) lastClickedTimer[2].className = 'text-primary';

    fetch('/api/task-start/', {
      method: 'POST',
      headers: { 'X-CSRFToken': getCookie('csrftoken') },
      body: new URLSearchParams({ task_id: lastClickedTimer[1] })
    })
    .then(r => r.json())
    .then((data) => {
      let kanbanItems = document.querySelectorAll('.kanban-item');
      if (!kanbanItems.length) kanbanItems = document.querySelectorAll('.card.shadow.mb-3');
      for (const kan of kanbanItems) {
        if (parseInt(kan.id, 10) === lastClickedTimer[1]) {
          updateActiveTimers([lastClickedTimer[1], data.time_spent], kan);
        }
      }
    })
    .catch(() => {
      const el = document.querySelector('a.text-primary');
      if (el) {
        el.className = 'text-black';
        (el.querySelector('i') || {}).className = 'fe fe-play';
      }
    });

    // и аккуратно скрываем сам тост
    hideToast();
  }
}

const KANBAN_SEL = {
  category: '.kanban-category',
  item: '.kanban-item',
  title: '.card-header-title',
  timeBlocks: '.col-auto.text-secondary small'
};

function findCategoryBy(employeeId, dateStr) {
  const cats = document.querySelectorAll(KANBAN_SEL.category);
  for (const c of cats) {
    if (String(c.id) === String(employeeId) && c.getAttribute('data-associated-date') === dateStr) {
      return c;
    }
  }
  return null;
}

function appendAtVisualEnd(container, node) {
  const cs = getComputedStyle(container);
  const isFlex = cs.display.includes('flex');
  const isReversed = isFlex && cs.flexDirection.includes('column-reverse');
  if (isReversed) container.prepend(node);
  else container.appendChild(node);
}

function insertCardByTime(container, node, seconds) {
  if (!Number.isFinite(seconds)) seconds = 0;
  if (seconds === 0) { appendAtVisualEnd(container, node); return; }
  const items = Array.from(container.querySelectorAll(KANBAN_SEL.item));
  const before = items.find(ch => {
    const holder = ch.querySelectorAll(KANBAN_SEL.timeBlocks)[1]?.closest('.col-auto.text-secondary')
                 || ch.querySelectorAll(KANBAN_SEL.timeBlocks)[0]?.closest('.col-auto.text-secondary');
    const t = Number(holder?.getAttribute('data-time'));
    return Number.isFinite(t) && t !== 0 && t > seconds;
  });
  if (before) container.insertBefore(node, before);
  else appendAtVisualEnd(container, node);
}

function updateCardTimeSeconds(node, seconds) {
  const blocks = node.querySelectorAll(KANBAN_SEL.timeBlocks);
  const display = blocks[1] || blocks[0];
  if (display) {
    // плановое время в секундах
    const holder = display.closest('.col-auto.text-secondary');
    if (holder) holder.setAttribute('data-time', String(seconds));
    display.textContent = float_to_time(seconds);
  }
}

function ensureCardExistsLike(sourceNode, id, attrs = {}) {
  let node = document.getElementById(String(id));
  if (node) return node;
  const clone = sourceNode.cloneNode(true);
  clone.id = String(id);
  if ('title' in attrs) {
    const t = clone.querySelector(KANBAN_SEL.title);
    if (t) t.textContent = attrs.title;
  }
  // ставим bitrix_id либо из attrs, либо наследуем от sourceNode (его ancestor)
  if ('bitrix' in attrs && attrs.bitrix) {
    clone.setAttribute('data-bs-bitrix', attrs.bitrix);
  } else {
    const fromSrc = getBitrixIdFromNode(sourceNode);
    if (fromSrc) clone.setAttribute('data-bs-bitrix', fromSrc);
  }
  if ('time' in attrs) updateCardTimeSeconds(clone, attrs.time);
  // сбросить “таймерные” классы/иконки на плей
  const playBtn = clone.querySelector('[data-action="play"], #playButton');
  if (playBtn) {
    playBtn.classList.remove('text-primary', 'text-warning');
    playBtn.classList.add('text-black');
    const playIcon = playBtn.querySelector('i');
    if (playIcon) playIcon.className = 'fe fe-play';
  }

  return clone;
}


function hideToast() {
  clearTimeout(toastHideTimeout); toastHideTimeout = null;
  clearInterval(timerInterval);   timerInterval = null;

  toastEl.classList.remove('show');
  // подожди окончание fade (200–300ms в твоей теме)
  setTimeout(() => {
    toastEl.style.display = 'none';
  }, 250);
}


function changeModalTime(num, modalId) {
    let s = [['#rangeTaskTimeHours','#rangeTaskTimeMinutes'], ['#emptyTaskTimeHours', '#emptyTaskTimeMinutes']]
    let hours = parseInt(document.querySelector(s[modalId][0]).value);
    if (Number.isNaN(hours)) {hours = 0}
    let minutes = parseInt(document.querySelector(s[modalId][1]).value);
    if (Number.isNaN(minutes)) {minutes = 0}
    console.log(hours, minutes)
    let sumTime = hours * 60 + minutes;
    console.log(sumTime);
    if (num == 1) { // +
        sumTime += 30;
    } else {
        sumTime -= 30;
    }
    console.log("Время после "+num+" "+sumTime)

    if (sumTime < 0) {sumTime = 0}
    if (sumTime > 2880) {sumTime = 2880}
    console.log("Время потом "+sumTime)

    document.querySelector(s[modalId][0]).value = Math.floor(sumTime / 60)
    document.querySelector(s[modalId][1]).value = sumTime % 60
}

function float_to_time(value) {
    if (!Number.isFinite(value)) return "0 минут";
    // Переводим секунды в минуты и округляем
    let total_minutes = Math.round(value / 60);
    let hours = Math.floor(total_minutes / 60);
    let minutes = total_minutes % 60;

    let parts = [];
    
    // Формируем часть с часами
    if (hours > 0) {
        let hour_word = hours === 1 ? "час" : 
                       (hours >= 2 && hours <= 4) ? "часа" : "часов";
        parts.push(hours + ' ' + hour_word);
    }

    // Формируем часть с минутами (если есть часы или минуты > 0)
    if (minutes > 0 || parts.length === 0) {
        let minute_word = minutes === 1 ? "минута" : 
                         (minutes >= 2 && minutes <= 4) ? "минуты" : "минут";
        parts.push(minutes + ' ' + minute_word);
    }

    return parts.length ? parts.join(" ") : "0 минут";
}

function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

function returnCorrectTime(minutes) {
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    
    if (hours === 0) {
        return `${mins} мин.`;
    }
    if (mins === 0) {
        return `${hours} ч.`;
    }
    return `${hours} ч. ${mins} мин.`;
}

function controlModal(timeInSecs, taskId) {
    const modal = document.querySelector('#modalTaskSplit')
    modal.dataset.taskId = String(taskId);           // ← источник истины
    modal.querySelector('#inputHidden').value = taskId; 

    let kanbans = document.querySelectorAll('.kanban-item');
    if (kanbans.length == 0) {
        kanbans = document.querySelectorAll('.card.shadow.mb-3')
    }
    for (let kan of kanbans) {
        if (kan.id == taskId) {
            lastClickedKanbanModal = kan;
            break;
        } 
    }
    console.log('lastClicked:', { id: lastClickedKanbanModal?.id, node: lastClickedKanbanModal });
}

// Функция для выхода из системы через AJAX
async function logout() {
    try {
        const response = await fetch('/logout/', {  // Убедитесь, что URL совпадает с вашим маршрутом
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken'),  // Функция для получения CSRF-токена
            },
            credentials: 'same-origin'
        });

        if (response.redirected) {
            window.location.href = response.url;  // Перенаправление на страницу входа
        } else if (!response.ok) {
            throw new Error('Ошибка при выходе из системы');
        }
    } catch (error) {
        console.error('Ошибка:', error);
        alert('Произошла ошибка при выходе из системы');
    }
}