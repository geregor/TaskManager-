let lastDraggableItem = null;
window.onload = (e) => {
    const scrollBlocks = document.querySelectorAll(".row.flex-nowrap.overflow-x-scroll");
    let isDraggingScroll = false;
    let startX, scrollLeft;
    let currentBlock = null;
    let isSyncing = false;
    

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

    document.addEventListener

    // Отдельная система для kanban-элементов
    const kanbanItems = document.querySelectorAll('.kanban-item');
    kanbanItems.forEach(item => {
        item.addEventListener('mousedown', () => {
            lastDraggableItem = item;

            // При начале drag kanban-элемента принудительно завершаем скролл
            if (isDraggingScroll) {
                handleScrollEnd();
            }
        });
    });

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


    // Очистка
    return () => {
        removeScrollListeners();
        kanbanItems.forEach(item => {
            item.removeEventListener('dragstart', () => {});
        });
    };
};

function taskDelegate() {
    console.log(lastDraggableItem)
}