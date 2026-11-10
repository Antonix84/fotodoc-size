/**
 * passport-photo.jsx — горячая клавиша внутри Photoshop.
 *
 * Назначение: сделать фотографию на документ по требованиям МВД. Ставится в
 * Photoshop как действие «выполнить сценарий», на кнопку — удобная
 * комбинация клавиш.
 *
 * Как это устроено. Распознавание лица и расчёт делает программа на Python
 * (в сборке — портативный exe, python в системе не нужен): на Python проще и
 * надёжнее, а в ExtendScript нет ни нужных библиотек, ни нормального окна
 * выбора размера. Photoshop отвечает за работу со слоями. Скрипты общаются
 * через папку с файлами:
 *
 *   job.txt        Photoshop → Python: какой документ обработать и куда выгрузил
 *   transform.txt  Python → Photoshop: поворот, масштаб, сдвиг и куда сохранить
 *   done.txt       Python → Photoshop: готово, вот путь и границы слоя
 *
 * Файл.execute в Photoshop 26.x больше не существует, поэтому программа
 * запускается через системную функцию system() и bat-файл.
 *
 * Рядом с этим файлом лежит passport_paths2.txt:
 *     exe=F:\...\passport.exe      портативная сборка
 *     python=...\python.exe        запуск из исходников, плюс
 *     program=F:/.../passport.py   строка program
 *     work=F:/.../passport_work    папка обмена
 *     auto_size=37x47              необязательно: тогда окно выбора не
 *                                   показывается, а Photoshop работает тихо
 * Его записывает passport.exe install (или tools\install_jsx.py).
 *
 * Имена у этой версии свои — passport-photo2.jsx и passport_paths2.txt — чтобы
 * не затирать скрипт прежней версии, который лежит в той же папке Photoshop.
 */

#target photoshop

var CONFIG_NAME = 'passport_paths2.txt';
var THIS_JSX = 'passport-photo2.jsx';
var JOB_NAME = 'job.txt';
var TRANSFORM_NAME = 'transform.txt';
var DONE_NAME = 'done.txt';
var TEMP_SOURCE = 'source.psd';

var POLL_MS = 250;
var WAIT_TRANSFORM_MS = 600000;   // 10 минут на окно выбора размера

// Модальные окна Photoshop надёжно вешают автоматизацию: при запуске через
// COM их невозможно закрыть программно. Поэтому на время работы диалоги
// выключаются. Задаётся ключом auto_size — это режим «без вопросов».
var QUIET = false;

// ── Файлы ───────────────────────────────────────────────────────────────────

function readParams(path) {
    var out = {};
    var f = new File(path);
    f.encoding = 'UTF-8';
    if (!f.open('r')) return null;
    var lines = f.read().split('\n');
    f.close();
    for (var i = 0; i < lines.length; i++) {
        var eq = lines[i].indexOf('=');
        if (eq < 0) continue;
        var key = lines[i].substring(0, eq);
        var value = lines[i].substring(eq + 1).replace(/^\s+/, '').replace(/\s+$/, '');
        if (value !== '') out[key] = value;
    }
    return out;
}

function writeParams(path, params) {
    var f = new File(path);
    f.encoding = 'UTF-8';
    if (!f.open('w')) throw new Error('не открылся для записи: ' + f.fsName);
    for (var key in params) {
        var value = String(params[key]);
        if (value !== '') f.writeln(key + '=' + value.replace(/[\r\n]/g, ' '));
    }
    f.close();
}

function deleteIfExists(path) {
    var f = new File(path);
    try { if (f.exists) f.remove(); } catch (e) { }
}

function waitForFile(path, timeoutMs) {
    var waited = 0;
    while (waited < timeoutMs) {
        if (new File(path).exists) return true;
        $.sleep(POLL_MS);
        waited += POLL_MS;
    }
    return false;
}

function clearWork(work) {
    deleteIfExists(work + '/' + JOB_NAME);
    deleteIfExists(work + '/' + TRANSFORM_NAME);
    deleteIfExists(work + '/' + DONE_NAME);
    deleteIfExists(work + '/' + TEMP_SOURCE);
    // Логи прошлых запусков тоже мешают: оставляем только самый свежий.
    var logs = [];
    try {
        var files = new Folder(work).getFiles();
        for (var i = 0; i < files.length; i++) {
            var f = files[i];
            if (f.name.indexOf('program-') === 0 && f.name.slice(-4) === '.log') {
                logs.push(f);
            }
        }
    } catch (e) { }
    logs.sort(function (a, b) { return a.modified - b.modified; });
    while (logs.length > 1) {
        try { logs.shift().remove(); } catch (e2) { }
    }
}

// След о том, где находится скрипт. Нужен, когда он «завис» без всякой ошибки:
// папка passport_work, файл trace.txt. Выключается одним числом.
var TRACE = false;

function trace(work, what) {
    if (!TRACE) return;
    try {
        var f = new File(work + '/trace.txt');
        f.encoding = 'UTF-8';
        f.open('a');
        f.writeln((new Date()).toLocaleString() + '  ' + what);
        f.close();
    } catch (e) { }
}

// ── Запуск программы ────────────────────────────────────────────────────────

var q = '"';      // кавычка для командных строк: экранировать её в ExtendScript
                  // нагляднее, чем городить \" внутри строк

/** Чем запускать программу: собранный exe или python со скриптом. */
function programArgs(cfg) {
    if (cfg.exe != null && cfg.exe !== '') return [cfg.exe];
    if (cfg.python != null && cfg.python !== '') {
        var args = [cfg.python];
        if (cfg.program != null && cfg.program !== '') args.push(cfg.program);
        return args;
    }
    return null;
}

/** Собирает строку запуска: "путь" "аргумент" … */
function commandLine(args, autoSize) {
    var parts = [];
    for (var i = 0; i < args.length; i++) {
        parts.push('"' + String(args[i]).replace(/"/g, '') + '"');
    }
    if (autoSize != null && autoSize !== '') {
        parts.push('"' + String(autoSize).replace(/"/g, '') + '"');
    }
    return parts.join(' ');
}

/**
 * Запускает программу и возвращает путь к журналу её вывода.
 *
 * Окно консоли не нужно: Photoshop ждёт результата, а чёрное окно мешает.
 * Используем VBScript с WindowStyle=0 для запуска без окна — это надёжнее,
 * чем bat с start: cmd.exe не остаётся висеть в процессах.
 */
function runProgram(args, runnerPath, autoSize, work) {
    // Имя лога — с меткой времени: иначе предыдущий запуск может держать файл
    // открытым, и перенаправление вывода не сработает.
    var stamp = (new Date()).getTime();
    var logPath = work + '/program-' + stamp + '.log';
    var line = commandLine(args, autoSize) + ' ' + q + '--log' + q + ' ' +
               q + logPath + q;

    // VBScript запускает программу без окна: CreateObject("WScript.Shell").Run
    // с WindowStyle=0 не создаёт консоли, а WaitOnReturn=False отпускает процесс.
    var vbs = new File(runnerPath);
    vbs.encoding = 'UTF-8';
    if (!vbs.open('w')) throw new Error('не удалось создать ' + vbs.fsName);
    vbs.write('CreateObject("WScript.Shell").Run "' + 
              line.replace(/"/g, '""') + '", 0, False\r\n');
    vbs.close();

    var command = 'wscript.exe ' + q + vbs.fsName + q;
    if (typeof system === 'function') {
        system(command);
    } else {
        File.execute(command);   // старые версии Photoshop
    }
    return logPath;
}

/** Самый свежий лог программы — нужен, когда что-то пошло не так. */
function latestLog(work) {
    var folder = new Folder(work);
    var newest = null;
    for (var i = 0; i < folder.files.length; i++) {
        var f = folder.files[i];
        if (f.name.indexOf('program-') !== 0 || f.name.slice(-4) !== '.log') {
            continue;
        }
        if (newest == null || f.modified > newest.modified) newest = f;
    }
    return newest;
}

// ── Сборка результата ───────────────────────────────────────────────────────

/**
 * Собирает фотографию на документе по числам из transform.txt.
 * Возвращает null при успехе или строку с ошибкой.
 */
function ppBuild(work, t, donePath) {
    var dialogsWere = app.displayDialogs;
    app.displayDialogs = DialogModes.NO;
    try {
        // 1. Документ под нужный размер: шаблон из папки программы или новый холст.
        //    Пустой template в задание не попадает — проверяем на отсутствие.
        var tpl;
        if (t.template != null && t.template !== '') {
            tpl = app.open(new File(t.template));
        } else {
            // Шестым аргументом Photoshop просит заливку из перечисления
            // DocumentFill — оставляем её по умолчанию: кадр всё равно
            // целиком закрывается фотографией.
            tpl = app.documents.add(UnitValue(t.docWidth, 'px'),
                                    UnitValue(t.docHeight, 'px'),
                                    parseFloat(t.ppi),
                                    'RGB',
                                    NewDocumentMode.RGB);
        }

        // 2. Рабочая копия фотографии: поворот и масштаб.
        //
        //    Поворот идёт через слой, масштаб — через холст документа. Так
        //    приходится делать из-за одной особенности: у resize слоя якорь
        //    берётся из перечисления AnchorType, а в этой версии Photoshop оно
        //    из сценария недоступно. Холст масштабируется без якоря, и так как
        //    слой занимал его целиком, получается ровно то, что нужно: масштаб
        //    от центра слоя.
        //
        //    В этой версии Photoshop у rotate и resizeImage только самые
        //    необходимые аргументы: поворот идёт вокруг центра слоя, а
        //    resizeImage задаёт размер холста в пикселях, сохраняя пропорции.
        //    Холст в программе пересчитывается заранее, поэтому масштабируем
        //    фотографию вместе с ним.
        //
        //    Единицы измерения указываем явно, через UnitValue. По документации
        //    (JavaScript Reference, resizeImage и translate) параметры — это
        //    UnitValue, и голое число значит «столько в единицах линейки».
        //    Если у человека линейка в сантиметрах или дюймах, запрос
        //    1456 × 2191 превращается в 1456 см × 2191 см, и Photoshop
        //    отвечает «результат может оказаться слишком большим». На одном
        //    компьютере работает, на другом нет — ровно эта ошибка.
        //
        //    Фоновый слой заблокирован — поворот такому слою недоступен,
        //    поэтому заранее делаем его обычным.
        var src = ppFindDoc(t.source);
        if (src == null) throw new Error('исходный документ не найден: ' + t.source);
        var work_doc = src.duplicate('рабочий', true);
        var layer = work_doc.activeLayer;
        if (layer.isBackgroundLayer) layer.isBackgroundLayer = false;
        layer.rotate(parseFloat(t.rotateDeg));
        var scale = parseFloat(t.scalePercent) / 100;
        work_doc.resizeImage(new UnitValue(Math.round(parseInt(t.sourceWidth, 10) * scale), 'px'),
                             new UnitValue(Math.round(parseInt(t.sourceHeight, 10) * scale), 'px'));

        // 3. Переносим слой в шаблон и ставим голову на место.
        //
        //    Куда именно Photoshop положит слой при переносе в другой документ,
        //    он не обещает: от размера холста это зависит. Поэтому положение не
        //    вычисляется на глаз — берём границы слоя и двигаем так, чтобы центр
        //    слоя оказался там, где его ждёт Python.
        app.activeDocument = work_doc;
        layer = layer.duplicate(tpl, ElementPlacement.PLACEATBEGINNING);
        app.activeDocument = tpl;
        layer.name = 'фото';
        if (layer.isBackgroundLayer) layer.isBackgroundLayer = false;

        var b = layer.bounds;
        var centerX = (b[0].as('px') + b[2].as('px')) / 2;
        var centerY = (b[1].as('px') + b[3].as('px')) / 2;
        // Здесь тоже UnitValue: сдвиг считаем в пикселях, и без явной единицы
        // Photoshop понял бы его в единицах линейки.
        layer.translate(new UnitValue(parseFloat(t.targetCx) - centerX, 'px'),
                        new UnitValue(parseFloat(t.targetCy) - centerY, 'px'));
        work_doc.close(SaveOptions.DONOTSAVECHANGES);

        // 5. Границы слоя — чтобы Python предупредил, если фотография не
        //    закрывает весь кадр. Читаем до flatten: после склейки слоёв ссылка
        //    на слой перестаёт быть рабочей.
        var b = layer.bounds;
        var left = String(b[0].as('px'));
        var top = String(b[1].as('px'));
        var right = String(b[2].as('px'));
        var bottom = String(b[3].as('px'));

        // 6. Склеиваем слои и сохраняем. asCopy = true: документ остаётся
        //    открытым под своим именем, шаблон и исходник не пострадали.
        tpl.flatten();
        var options;
        if (t.format === 'PSD') {
            options = new PhotoshopSaveOptions();
            options.layers = false;
        } else if (t.format === 'TIFF') {
            options = new TiffSaveOptions();
            options.layers = false;
            options.imageCompression = TiffSaveOptions.LZW;
        } else {
            options = new JPEGSaveOptions();
            options.quality = parseInt(t.quality, 10);
            options.matte = MatteType.NONE;
        }
        tpl.saveAs(new File(t.result), options, true, Extension.LOWERCASE);

        writeParams(donePath, {
            ok: '1',
            result: t.result,
            left: left,
            top: top,
            right: right,
            bottom: bottom,
            docWidth: t.docWidth,
            docHeight: t.docHeight
        });
        return null;
    } catch (e) {
        return e.toString() + ' (строка ' + e.line + ')';
    } finally {
        app.displayDialogs = dialogsWere;
    }
}

function ppFindDoc(name) {
    var lower = name.toLowerCase();
    for (var i = 0; i < app.documents.length; i++) {
        if (app.documents[i].name.toLowerCase() === lower) return app.documents[i];
    }
    return null;
}

// ── Основной ход ────────────────────────────────────────────────────────────

function main() {
    var here = new File($.fileName).parent;
    var cfg = readParams(here.fsName + '/' + CONFIG_NAME);
    QUIET = cfg != null && cfg.auto_size != null;
    var args = cfg != null ? programArgs(cfg) : null;
    if (args == null) {
        if (!QUIET) {
            alert('Рядом со скриптом нет ' + CONFIG_NAME + ' с путями, либо в ' +
                  'нём нет строки exe= или python=.\n\n' +
                  'Что сделать: запустите  passport.exe install\n' +
                  'Программа сама найдёт Photoshop и положит рядом с ним\n' +
                  THIS_JSX + ' и ' + CONFIG_NAME + '.\n\n' +
                  'Если запускаете из исходников:  python tools\\install_jsx.py\n\n' +
                  'Внимание: ' + 'passport_paths.txt' + ' — это файл прежней ' +
                  'версии, программа его не читает.');
        }
        return;
    }

    // Папка работы. Скрипт живёт в папке Photoshop, а программа — рядом с
    // проектом, поэтому путь берём из настроек: так общаются обе стороны.
    var work = new Folder(cfg.work != null ? cfg.work : here.fsName + '/passport_work');
    if (!work.exists) work.create();

    var jobPath = work.fsName + '/' + JOB_NAME;
    var transformPath = work.fsName + '/' + TRANSFORM_NAME;
    var donePath = work.fsName + '/' + DONE_NAME;
    clearWork(work.fsName);

    if (app.documents.length === 0) {
        if (!QUIET) alert('Откройте фотографию в Photoshop — обрабатывать нечего.');
        return;
    }

    // 1. Выгружаем копию активного документа во временный PSD. Сам исходник не
    //    трогаем: ни переименования, ни сохранения поверх.
    var src = app.activeDocument;
    var tempPsd = work.fsName + '/' + TEMP_SOURCE;
    var dialogsWere = app.displayDialogs;
    app.displayDialogs = DialogModes.NO;
    try {
        var analysis = src.duplicate(src.name + '-анализ', true);
        var psdOptions = new PhotoshopSaveOptions();
        psdOptions.layers = false;
        analysis.saveAs(new File(tempPsd), psdOptions, true, Extension.LOWERCASE);
        analysis.close(SaveOptions.DONOTSAVECHANGES);
    } catch (e) {
        app.displayDialogs = dialogsWere;
        if (!QUIET) {
            alert('Не удалось выгрузить фотографию для разбора:\n' + e.toString());
        }
        return;
    }
    app.displayDialogs = dialogsWere;

    // 2. Просим программу разобрать кадр и посчитать трансформацию.
    writeParams(jobPath, {
        source: src.name,
        temp: tempPsd,
        work: work.fsName,
        sourcePath: src.fullName.fsName
    });
    // vbs пишем в папку работы: папка Photoshop может быть недоступна для записи.
    runProgram(args, work.fsName + '/passport_run.vbs',
                cfg.auto_size, work.fsName);

    if (!waitForFile(transformPath, WAIT_TRANSFORM_MS)) {
        if (!QUIET) {
            alert('Программа не ответила. Посмотрите файлы program-*.log ' +
                  'в папке работы или запустите вручную:\n"' + args.join('" "') +
                  '"');
        }
        clearWork(work.fsName);
        return;
    }
    var t = readParams(transformPath);
    if (t == null || t.cancel === '1') {   // пользователь закрыл окно выбора
        clearWork(work.fsName);
        return;
    }

    // 3. Собираем результат.
    var error = ppBuild(work, t, donePath);
    deleteIfExists(jobPath);
    deleteIfExists(transformPath);
    deleteIfExists(tempPsd);
    if (error != null) {
        // done.txt с ошибкой оставляем: его читает Python. Убирать его вместе с
        // остальным нельзя — иначе причина сбоя пропадает бесследно.
        writeParams(donePath, {ok: '0', error: error});
        if (!QUIET) {
            alert('Не получилось сделать фотографию:\n' + error);
        }
    }
    // При успехе файл done.txt убирает Python — он его ещё читает.
}

main();
