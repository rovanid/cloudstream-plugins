package com.cloudstreamid.otakudesuprovider

import android.content.Context
import com.lagradost.cloudstream3.plugins.CloudstreamPlugin
import com.lagradost.cloudstream3.plugins.Plugin

@CloudstreamPlugin
class OtakudesuPlugin : Plugin() {
    override fun load(context: Context) {
        registerMainAPI(OtakudesuProvider())
    }
}
