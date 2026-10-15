package com.cloudstreamid.sflixprovider

import android.content.Context
import com.lagradost.cloudstream3.plugins.CloudstreamPlugin
import com.lagradost.cloudstream3.plugins.Plugin

@CloudstreamPlugin
class SFlixPlugin : Plugin() {
    override fun load(context: Context) {
        registerMainAPI(SFlixProvider())
    }
}
