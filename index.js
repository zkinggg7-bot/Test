const axios = require('axios');
const cheerio = require('cheerio');
const iconv = require('iconv-lite');

const targetUrl = 'https://www.69shuba.com/txt/87906/39867326';

async function scrapeWithProxyAndCookies() {
    try {
        console.log(`[LOG] محاولة تجاوز الحظر باستخدام وسيط (Proxy) وكوكيز حقيقي...`);

        // الكوكيز المستخرج من صورك لضمان الهوية البشرية
        const cookieString = [
            'zh_choose=s',
            'shuba=10814-11633-20856-3178',
            'jieqiHistory=87906-39867326-%25u7B2C1%25u7AE0%2520%25u674E%25u6155%25u751F-1767886344',
            '_ga=GA1.1.2076534855.1767884557',
            '_sharedID=3801fe8a-709a-49e0-a6c8-dde12225ee31'
        ].join('; ');

        // سنستخدم بروكسي "شفاف" كبداية، إذا لم ينجح سنحاول استخدام خدمة بروكشي مجانية
        const instance = axios.create({
            timeout: 20000,
            responseType: 'arraybuffer',
            headers: {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Cookie': cookieString,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9',
                'Referer': 'https://www.69shuba.com/',
                'X-Forwarded-For': '1.1.1.1' // محاولة تزييف مصدر الطلب كأنه من Cloudflare
            }
        });

        const response = await instance.get(targetUrl);
        const decodedHtml = iconv.decode(response.data, 'gbk');
        const $ = cheerio.load(decodedHtml);

        const title = $('h1').last().text().trim();
        
        if (!title || decodedHtml.includes('403 Forbidden')) {
             // إذا فشل، سنحاول عبر خدمة تحويل طلبات (Proxy API) مجانية بسيطة
             console.log("[LOG] الـ IP لا يزال محظوراً، أحاول عبر وسيط خارجي...");
             return await scrapeViaExternalProxy(cookieString);
        }

        $('.txtnav script, .txtnav .contentadv, .txtnav .txtinfo, .txtnav h1').remove();
        let content = $('.txtnav').text();
        content = content.replace(/\(本章完\)/g, '').replace(/\n\s*\n/g, '\n\n').trim();

        console.log(`[SUCCESS] تم كسر الحظر بنجاح! الفصل: ${title}`);
        
        return { status: 'success', title, content: content.substring(0, 500) + "..." };

    } catch (error) {
        console.error(`[ERROR] فشل: ${error.message}`);
        return { status: 'error', message: error.message };
    }
}

// دالة احتياطية تستخدم وسيطاً خارجياً إذا فشل الاتصال المباشر
async function scrapeViaExternalProxy(cookies) {
    try {
        // نستخدم خدمة AllOrigins كمثال لوسيط مجاني
        const proxyUrl = `https://api.allorigins.win/get?url=${encodeURIComponent(targetUrl)}`;
        const response = await axios.get(proxyUrl);
        const data = response.data;
        
        // ملاحظة: AllOrigins يعيد البيانات كـ String في حقل contents
        const $ = cheerio.load(data.contents);
        const title = $('h1').last().text().trim();

        if (title) {
            return { status: 'success', title, via: 'Proxy', message: 'تم الجلب عبر وسيط خارجي' };
        }
        throw new Error("الموقع محصن جداً حتى ضد الوسطاء المجانيين.");
    } catch (e) {
        return { status: 'error', message: "الحظر شامل: الموقع يرفض Railway والوسطاء المجانيين." };
    }
}

const http = require('http');
const server = http.createServer(async (req, res) => {
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    if (req.url === '/test') {
        const result = await scrapeWithProxyAndCookies();
        res.end(JSON.stringify(result, null, 2));
    } else {
        res.end(JSON.stringify({ message: 'Hybrid Scraper is Active', endpoint: '/test' }));
    }
});

const PORT = process.env.PORT || 8080;
server.listen(PORT, () => {
    console.log(`Server started on port ${PORT}`);
});
